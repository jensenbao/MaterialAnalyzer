"""Shared runtime helpers for MaterialAnalyzer Python tooling."""

from __future__ import annotations

import locale
import os
import socket
import subprocess
import time
import webbrowser

import unreal


STREAMLIT_HOST = "127.0.0.1"
STREAMLIT_PORT = 8501
STREAMLIT_URL = f"http://{STREAMLIT_HOST}:{STREAMLIT_PORT}"

PLUGIN_PY_DIR = os.path.dirname(__file__)
VENV_DIR = os.path.join(PLUGIN_PY_DIR, ".venv")
VENV_PYTHON = os.path.join(VENV_DIR, "Scripts", "python.exe")
REQ_FILE = os.path.join(PLUGIN_PY_DIR, "requirements_streamlit.txt")


class ProgressContext:
    def __init__(self, title: str):
        self._task = None
        self._last_progress = 0.0
        scoped = getattr(unreal, "ScopedSlowTask", None)
        if scoped:
            try:
                self._task = scoped(100.0, title)
                self._task.make_dialog(True)
            except Exception:
                self._task = None

    def update(self, progress: float, message: str) -> bool:
        if not self._task:
            return True

        progress = max(0.0, min(99.0, progress))
        delta = max(progress - self._last_progress, 0.1)
        self._last_progress = progress

        try:
            self._task.enter_progress_frame(delta, message)
            if self._task.should_cancel():
                return False
        except Exception:
            return True
        return True

    def complete(self, message: str = "完成") -> None:
        if not self._task:
            return
        try:
            remaining = max(100.0 - self._last_progress, 0.1)
            self._task.enter_progress_frame(remaining, message)
        except Exception:
            pass


def is_port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def resolve_venv_python() -> str:
    if os.path.exists(VENV_PYTHON):
        return VENV_PYTHON

    raise RuntimeError(f"Plugin venv python not found: {VENV_PYTHON}")


def resolve_venv_pythonw() -> str:
    pythonw = os.path.join(VENV_DIR, "Scripts", "pythonw.exe")
    if os.path.exists(pythonw):
        return pythonw
    return resolve_venv_python()


def ensure_virtualenv() -> dict:
    if os.path.exists(VENV_PYTHON):
        return {"ok": True, "created": False, "venv_dir": VENV_DIR, "python": VENV_PYTHON}

    setup_script = os.path.normpath(os.path.join(PLUGIN_PY_DIR, "..", "..", "setup_python_env.ps1"))
    return {
        "ok": False,
        "error": "venv_missing",
        "detail": VENV_PYTHON,
        "hint": f"Run setup script first: {setup_script}",
    }


def run_subprocess(
    command: list[str],
    env: dict | None = None,
    cwd: str | None = None,
    progress_title: str | None = None,
    expected_seconds: float = 120.0,
    hard_timeout_seconds: float | None = None,
) -> tuple[bool, str]:
    startupinfo = None
    creationflags = 0
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)

    progress = ProgressContext(progress_title) if progress_title else None

    try:
        preferred_encoding = locale.getpreferredencoding(False) or "utf-8"
        proc = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding=preferred_encoding,
            errors="replace",
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
    except Exception as exc:
        return False, str(exc)

    start_time = time.time()
    while proc.poll() is None:
        elapsed = time.time() - start_time
        if hard_timeout_seconds and elapsed > hard_timeout_seconds:
            try:
                proc.terminate()
                time.sleep(0.3)
                if proc.poll() is None:
                    proc.kill()
            except Exception:
                pass
            return False, f"timeout after {int(hard_timeout_seconds)}s"

        if progress:
            pct = (elapsed / max(expected_seconds, 1.0)) * 90.0
            if not progress.update(pct, f"{progress_title}（已用时 {int(elapsed)} 秒）"):
                try:
                    proc.terminate()
                except Exception:
                    pass
                return False, "user_cancelled"
        time.sleep(0.2)

    stdout, stderr = proc.communicate()
    if proc.returncode == 0:
        if progress:
            progress.complete("完成")
        return True, (stdout or "").strip()

    if progress:
        progress.complete("失败")

    stderr = (stderr or "").strip()
    stdout = (stdout or "").strip()
    return False, stderr or stdout or f"exit_code={proc.returncode}"


def ensure_runtime_dependencies() -> dict:
    if not os.path.exists(REQ_FILE):
        return {"ok": False, "error": f"requirements not found: {REQ_FILE}"}

    venv_state = ensure_virtualenv()
    if not venv_state.get("ok"):
        return {"ok": False, "error": "venv_setup_failed", "detail": venv_state}

    py_exe = venv_state["python"]
    env = os.environ.copy()
    env["PYTHONPATH"] = PLUGIN_PY_DIR + os.pathsep + env.get("PYTHONPATH", "")

    check_cmd = [py_exe, "-c", "import streamlit, requests, pandas"]
    check_ok, _ = run_subprocess(check_cmd, env=env)
    if check_ok:
        return {"ok": True, "installed": False, "venv_dir": VENV_DIR, "python": py_exe}

    setup_script = os.path.normpath(os.path.join(PLUGIN_PY_DIR, "..", "..", "setup_python_env.ps1"))
    return {
        "ok": False,
        "error": "dependencies_missing",
        "detail": "streamlit/requests/pandas not installed",
        "hint": f"Run setup script first: {setup_script}",
        "venv_dir": VENV_DIR,
        "python": py_exe,
    }


def ensure_streamlit_server(show_progress: bool = False, wait_timeout_seconds: float = 12.0) -> dict:
    if is_port_open(STREAMLIT_HOST, STREAMLIT_PORT):
        return {"ok": True, "running": True, "started": False}

    deps = ensure_runtime_dependencies()
    if not deps.get("ok"):
        return {"ok": False, "error": "dependency_setup_failed", "detail": deps}

    py_exe = resolve_venv_pythonw()
    app_py = os.path.join(PLUGIN_PY_DIR, "material_analyzer_streamlit_app.py")
    if not os.path.exists(app_py):
        return {"ok": False, "error": f"streamlit app not found: {app_py}"}

    env = os.environ.copy()
    env["PYTHONPATH"] = PLUGIN_PY_DIR + os.pathsep + env.get("PYTHONPATH", "")

    cmd = [
        py_exe,
        "-m",
        "streamlit",
        "run",
        app_py,
        "--server.headless",
        "true",
        "--server.port",
        str(STREAMLIT_PORT),
        "--browser.gatherUsageStats",
        "false",
    ]

    creationflags = (
        getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )

    try:
        subprocess.Popen(
            cmd,
            cwd=PLUGIN_PY_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
            env=env,
        )
    except Exception as exc:
        return {"ok": False, "error": f"failed to launch streamlit: {exc}"}

    if wait_timeout_seconds <= 0:
        return {"ok": True, "running": False, "started": True, "pending": True}

    progress = ProgressContext("MaterialAnalyzer 正在启动 Web 服务") if show_progress else None
    deadline = time.time() + wait_timeout_seconds
    while time.time() < deadline:
        if is_port_open(STREAMLIT_HOST, STREAMLIT_PORT):
            if progress:
                progress.complete("Web 服务已就绪")
            return {"ok": True, "running": True, "started": True}
        if progress:
            elapsed = max(0.0, wait_timeout_seconds - (deadline - time.time()))
            if not progress.update(
                (elapsed / max(wait_timeout_seconds, 1.0)) * 95.0,
                f"MaterialAnalyzer 正在启动 Web 服务（{int(elapsed)} 秒）",
            ):
                return {"ok": False, "error": "user_cancelled"}
        time.sleep(0.25)

    if progress:
        progress.complete("启动超时")

    return {"ok": False, "error": "streamlit did not open port 8501 in time"}


def open_url(url: str) -> bool:
    try:
        if webbrowser.open(url, new=2):
            return True
    except Exception:
        pass

    try:
        os.startfile(url)  # type: ignore[attr-defined]
        return True
    except Exception:
        pass

    try:
        unreal.SystemLibrary.launch_url(url)
        return True
    except Exception:
        return False