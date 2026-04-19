# pyright: reportMissingImports=false

"""UE-side HTTP bridge service for Streamlit analyzer.

Run inside Unreal Python environment.
"""

from __future__ import annotations

import json
import queue
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import unreal


def get_selected_material_name() -> str:
    assets = unreal.EditorUtilityLibrary.get_selected_assets()
    for asset in assets:
        try:
            if isinstance(asset, unreal.Material):
                return asset.get_path_name()
        except Exception:
            pass

        # Also accept material instances/interfaces where Unreal may not expose
        # a stable Python class check across versions.
        try:
            class_name = asset.get_class().get_name()
            if class_name.startswith("Material"):
                return asset.get_path_name()
        except Exception:
            pass

        # Last resort: if this asset can resolve to a base material, accept it.
        try:
            base_mat = _resolve_base_material(asset)
            if base_mat:
                return asset.get_path_name()
        except Exception:
            pass
    raise RuntimeError("No Material selected in Content Browser")


def _get_material_expressions(material: unreal.Material) -> list:
    """Get material expression nodes with UE-version-compatible fallbacks."""
    # UE5.6 C++ API exposes GetExpressions/GetExpressionCollection paths; Python exposure differs by build.

    # Method call path: material.get_expressions()
    try:
        method = getattr(material, "get_expressions", None)
        if callable(method):
            expressions = method()
            if expressions:
                return list(expressions)
    except Exception:
        pass

    # Preferred path for UE5.3+: read editor property directly.
    try:
        expressions = material.get_editor_property("expressions")
        if expressions:
            return list(expressions)
    except Exception:
        pass

    # Fallback: direct attribute access.
    try:
        expressions = getattr(material, "expressions", None)
        if expressions:
            return list(expressions)
    except Exception:
        pass

    # Fallback: expression_collection on material.
    try:
        method = getattr(material, "get_expression_collection", None)
        if callable(method):
            expression_collection = method()
        else:
            expression_collection = material.get_editor_property("expression_collection")
        if expression_collection:
            expressions = expression_collection.get_editor_property("expressions")
            if expressions:
                return list(expressions)
    except Exception:
        pass

    # Fallback: editor_only_data -> expression_collection -> expressions.
    try:
        method = getattr(material, "get_editor_only_data", None)
        if callable(method):
            editor_only_data = method()
        else:
            editor_only_data = material.get_editor_property("editor_only_data")
        if editor_only_data:
            expression_collection = editor_only_data.get_editor_property("expression_collection")
            if expression_collection:
                expressions = expression_collection.get_editor_property("expressions")
                if expressions:
                    return list(expressions)
    except Exception:
        pass

    # Optional fallback for engines that expose this helper.
    try:
        method = getattr(unreal.MaterialEditingLibrary, "get_material_expressions", None)
        if callable(method):
            expressions = method(material)
            if expressions:
                return list(expressions)
    except Exception:
        pass

    return []


def _resolve_base_material(asset):
    if isinstance(asset, unreal.Material):
        return asset

    # Try material interface helper methods first.
    try:
        method = getattr(asset, "get_base_material", None)
        if callable(method):
            mat = method()
            if isinstance(mat, unreal.Material):
                return mat
    except Exception:
        pass

    try:
        method = getattr(asset, "get_material", None)
        if callable(method):
            mat = method()
            if isinstance(mat, unreal.Material):
                return mat
    except Exception:
        pass

    return None


def _material_to_graph(material: unreal.Material) -> dict:
    expressions = _get_material_expressions(material)
    nodes = []

    material_info = {
        "path": "",
        "name": "",
        "domain": "",
        "blend_mode": "",
        "two_sided": False,
    }

    try:
        material_info["path"] = material.get_path_name()
    except Exception:
        pass

    try:
        material_info["name"] = material.get_name()
    except Exception:
        pass

    try:
        material_info["domain"] = str(material.get_editor_property("material_domain"))
    except Exception:
        pass

    try:
        material_info["blend_mode"] = str(material.get_editor_property("blend_mode"))
    except Exception:
        pass

    try:
        material_info["two_sided"] = bool(material.get_editor_property("two_sided"))
    except Exception:
        pass

    for idx, expr in enumerate(expressions):
        node_id = f"node_{idx + 1}"
        node_name = expr.get_name() if hasattr(expr, "get_name") else node_id
        node_type = expr.get_class().get_name() if hasattr(expr, "get_class") else "Unknown"

        nodes.append(
            {
                "id": node_id,
                "name": node_name,
                "type": node_type,
                "params": {},
            }
        )

    return {
        "material_name": material_info["name"],
        "source_type": "ue_api",
        "material": material_info,
        "nodes": nodes,
        "edges": [],
        "property_bindings": [],
        "comments": [],
        "stats": {
            "node_count": len(nodes),
            "edge_count": 0,
            "binding_count": 0,
            "comment_count": 0,
        },
        "meta": {
            "material_name": material_info["name"],
            "material_path": material_info["path"],
        },
    }


def export_selected_material_graph() -> dict:
    assets = unreal.EditorUtilityLibrary.get_selected_assets()
    for asset in assets:
        base_mat = _resolve_base_material(asset)
        if base_mat:
            return _material_to_graph(base_mat)
    raise RuntimeError("No Material selected in Content Browser")


def export_material_graph_by_name(name: str) -> dict:
    asset = unreal.load_asset(name)
    if asset is None:
        raise RuntimeError(f"Material not found: {name}")
    base_mat = _resolve_base_material(asset)
    if not base_mat:
        raise RuntimeError(f"Asset is not a Material: {name}")
    return _material_to_graph(base_mat)


def _parse_plugin_json(raw: str) -> dict:
    if not raw:
        return {"ok": False, "error_type": "empty_payload", "message": "Plugin returned empty payload"}

    try:
        parsed = json.loads(raw)
    except Exception:
        return {
            "ok": False,
            "error_type": "invalid_json",
            "message": "Plugin returned non-JSON payload",
            "raw": raw,
        }

    if isinstance(parsed, dict):
        return parsed
    return {"ok": False, "error_type": "invalid_payload", "message": "Plugin payload must be an object"}


def export_selected_material_summary_cpp() -> dict:
    try:
        raw = unreal.MaterialAnalyzerBPLibrary.get_selected_material_summary_json()
        return _parse_plugin_json(raw)
    except Exception as exc:
        return {
            "ok": False,
            "error_type": "cpp_bridge_exception",
            "message": str(exc),
        }


def export_material_summary_cpp(material_path: str) -> dict:
    try:
        raw = unreal.MaterialAnalyzerBPLibrary.get_material_summary_json(material_path)
        return _parse_plugin_json(raw)
    except Exception as exc:
        return {
            "ok": False,
            "error_type": "cpp_bridge_exception",
            "message": str(exc),
        }


def export_material_with_fallback(material_path: str | None = None, use_cpp: bool = False) -> dict:
    selected_path = _resolve_selected_material_path()
    resolved_path = (material_path or "").strip() or selected_path
    if not resolved_path:
        return {
            "ok": False,
            "error_type": "selection_empty",
            "message": "No material path available. Select a material before starting bridge, or pass /material_summary?path=...",
            "selected_material_path": selected_path,
            "cpp_attempted": bool(use_cpp),
            "cpp_ok": False,
        }

    cpp_result = None
    cpp_error = None

    if use_cpp:
        cpp_result = (
            export_material_summary_cpp(resolved_path)
        )
        if cpp_result.get("ok"):
            cpp_result.setdefault("resolved_material_path", resolved_path)
            cpp_result.setdefault("selected_material_path", selected_path)
            cpp_result.setdefault("cpp_attempted", True)
            cpp_result.setdefault("cpp_ok", True)
            return cpp_result
        cpp_error = cpp_result

    try:
        graph = export_material_graph_by_name(resolved_path)
        graph.update(
            {
                "ok": True,
                "source": "ue_api",
                "source_type": graph.get("source_type", "ue_api"),
                "resolved_material_path": resolved_path,
                "selected_material_path": selected_path,
                "cpp_attempted": bool(use_cpp),
                "cpp_ok": False,
            }
        )
        if cpp_error:
            graph["fallback_from"] = "cpp_graph"
            graph["fallback_reason"] = cpp_error.get("error_type", "unknown")
            graph["fallback_message"] = cpp_error.get("message", "unknown")
        return graph
    except Exception as exc:
        return {
            "ok": False,
            "error_type": (cpp_error or {}).get("error_type", "fallback_failed"),
            "message": (cpp_error or {}).get("message", str(exc)),
            "fallback": "use_pasted_text",
            "resolved_material_path": resolved_path,
            "selected_material_path": selected_path,
            "cpp_attempted": bool(use_cpp),
            "cpp_ok": False,
        }


_UE_BRIDGE_GLOBALS = {
    "unreal": unreal,
    "get_selected_material_name": get_selected_material_name,
    "export_selected_material_graph": export_selected_material_graph,
    "export_material_graph_by_name": export_material_graph_by_name,
    "export_selected_material_summary_cpp": export_selected_material_summary_cpp,
    "export_material_summary_cpp": export_material_summary_cpp,
    "export_material_with_fallback": export_material_with_fallback,
}


_GAME_THREAD_QUEUE: queue.Queue = queue.Queue()
_UE_BRIDGE_TICK_HANDLE = None
_UE_BRIDGE_TICK_KIND = ""
_UE_BRIDGE_LAST_TICK_THREAD_ID = 0
_LAST_SELECTED_MATERIAL_PATH = ""


def _resolve_selected_material_path() -> str:
    """Resolve selected material path at request time and keep cache in sync."""
    global _LAST_SELECTED_MATERIAL_PATH

    try:
        selected_path = get_selected_material_name().strip()
        if selected_path:
            _LAST_SELECTED_MATERIAL_PATH = selected_path
            return selected_path
    except Exception:
        pass

    return (_LAST_SELECTED_MATERIAL_PATH or "").strip()


def get_selected_material_debug(include_cpp: bool = False) -> dict:
    """Return detailed selection diagnostics for bridge and plugin routing."""
    assets = unreal.EditorUtilityLibrary.get_selected_assets()
    items = []

    for asset in assets:
        item = {
            "asset_path": "",
            "asset_name": "",
            "asset_class": "",
            "base_material_path": "",
        }

        try:
            item["asset_path"] = asset.get_path_name()
        except Exception:
            pass

        try:
            item["asset_name"] = asset.get_name()
        except Exception:
            pass

        try:
            item["asset_class"] = asset.get_class().get_name()
        except Exception:
            pass

        try:
            base_mat = _resolve_base_material(asset)
            if base_mat:
                item["base_material_path"] = base_mat.get_path_name()
        except Exception:
            pass

        items.append(item)

    payload = {
        "ok": True,
        "selected_count": len(items),
        "selected_items": items,
        "selected_material_path": _resolve_selected_material_path(),
        "cached_material_path": (_LAST_SELECTED_MATERIAL_PATH or "").strip(),
    }

    if include_cpp:
        try:
            payload["cpp_selected_summary"] = export_selected_material_summary_cpp()
        except Exception as exc:
            payload["cpp_selected_summary"] = {
                "ok": False,
                "error_type": "cpp_bridge_exception",
                "message": str(exc),
            }

    return payload


_UE_BRIDGE_GLOBALS["get_selected_material_debug"] = get_selected_material_debug


def _pump_game_thread_queue(_delta_seconds: float) -> None:
    global _UE_BRIDGE_LAST_TICK_THREAD_ID
    _UE_BRIDGE_LAST_TICK_THREAD_ID = threading.get_ident()

    while True:
        try:
            task = _GAME_THREAD_QUEUE.get_nowait()
        except queue.Empty:
            break

        func, args, kwargs, done_event, holder = task
        try:
            holder["result"] = func(*args, **kwargs)
        except Exception as exc:
            holder["error"] = str(exc)
            holder["trace"] = traceback.format_exc()
            holder["tick_thread_id"] = _UE_BRIDGE_LAST_TICK_THREAD_ID
        finally:
            done_event.set()


def _run_on_game_thread_sync(func, *args, timeout: float = 10.0, **kwargs):
    done_event = threading.Event()
    holder = {}
    _GAME_THREAD_QUEUE.put((func, args, kwargs, done_event, holder))

    if not done_event.wait(timeout):
        raise TimeoutError("Timed out waiting for game-thread execution")

    if "error" in holder:
        raise RuntimeError(holder.get("error", "Unknown game-thread error"))

    return holder.get("result")


class UEBridgeHandler(BaseHTTPRequestHandler):
    def _send_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            if path == "/health":
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "service": "ue-bridge",
                        "tick_kind": _UE_BRIDGE_TICK_KIND,
                        "tick_thread_id": _UE_BRIDGE_LAST_TICK_THREAD_ID,
                        "queue_size": _GAME_THREAD_QUEUE.qsize(),
                    },
                )
                return

            if path == "/selected_material_summary":
                use_cpp = ((query.get("use_cpp") or ["1"])[0].strip() in ("1", "true", "True"))
                payload = _run_on_game_thread_sync(export_material_with_fallback, None, use_cpp=use_cpp)
                self._send_json(200, payload)
                return

            if path == "/debug_selected":
                include_cpp = ((query.get("include_cpp") or ["0"])[0].strip() in ("1", "true", "True"))
                payload = _run_on_game_thread_sync(get_selected_material_debug, include_cpp)
                self._send_json(200, payload)
                return

            if path == "/material_summary":
                material_path = (query.get("path") or [""])[0].strip()
                if not material_path:
                    self._send_json(400, {"ok": False, "error_type": "invalid_request", "message": "Query parameter 'path' is required"})
                    return
                use_cpp = ((query.get("use_cpp") or ["1"])[0].strip() in ("1", "true", "True"))
                payload = _run_on_game_thread_sync(export_material_with_fallback, material_path, use_cpp=use_cpp)
                self._send_json(200, payload)
                return

            if path == "/material_export_with_fallback":
                material_path = (query.get("path") or [""])[0].strip()
                use_cpp = ((query.get("use_cpp") or ["1"])[0].strip() in ("1", "true", "True"))
                payload = _run_on_game_thread_sync(export_material_with_fallback, material_path or None, use_cpp=use_cpp)
                self._send_json(200, payload)
                return

            self._send_json(404, {"error": "not found"})
        except Exception as exc:
            self._send_json(
                500,
                {
                    "ok": False,
                    "error_type": "bridge_handler_exception",
                    "message": str(exc),
                    "trace": traceback.format_exc(),
                },
            )

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/run_python":
            self._send_json(404, {"error": "not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            request_data = json.loads(raw) if raw else {}
            code = request_data.get("code", "")

            local_vars = {}
            exec(code, _UE_BRIDGE_GLOBALS, local_vars)

            if "result" in local_vars:
                result = local_vars["result"]
                payload = result if isinstance(result, dict) else {"result": result}
            else:
                payload = {"ok": True}

            self._send_json(200, payload)
        except Exception as exc:
            self._send_json(
                500,
                {
                    "error": str(exc),
                    "trace": traceback.format_exc(),
                },
            )


def start_bridge(host: str = "127.0.0.1", port: int = 30010) -> dict:
    global _UE_BRIDGE_SERVER, _UE_BRIDGE_THREAD, _UE_BRIDGE_TICK_HANDLE, _UE_BRIDGE_TICK_KIND, _LAST_SELECTED_MATERIAL_PATH

    try:
        if _UE_BRIDGE_SERVER is not None:
            bound_host, bound_port = _UE_BRIDGE_SERVER.server_address
            thread_alive = _UE_BRIDGE_THREAD is not None and _UE_BRIDGE_THREAD.is_alive()
            if thread_alive and str(bound_host) == str(host) and int(bound_port) == int(port):
                selected_path = _resolve_selected_material_path()
                message = f"UE Bridge already running at http://{host}:{port}"
                if selected_path:
                    message += f" (selection: {selected_path})"
                unreal.log(message)
                return {"ok": True, "message": message, "already_running": True}

            _UE_BRIDGE_SERVER.shutdown()
            _UE_BRIDGE_SERVER.server_close()
    except Exception:
        pass

    _UE_BRIDGE_SERVER = ThreadingHTTPServer((host, port), UEBridgeHandler)
    _UE_BRIDGE_THREAD = threading.Thread(target=_UE_BRIDGE_SERVER.serve_forever, daemon=True)
    _UE_BRIDGE_THREAD.start()

    try:
        _LAST_SELECTED_MATERIAL_PATH = get_selected_material_name()
    except Exception:
        _LAST_SELECTED_MATERIAL_PATH = ""

    if _UE_BRIDGE_TICK_HANDLE is None:
        register_pre = getattr(unreal, "register_slate_pre_tick_callback", None)
        register_post = getattr(unreal, "register_slate_post_tick_callback", None)
        if callable(register_pre):
            _UE_BRIDGE_TICK_HANDLE = register_pre(_pump_game_thread_queue)
            _UE_BRIDGE_TICK_KIND = "pre"
        elif callable(register_post):
            _UE_BRIDGE_TICK_HANDLE = register_post(_pump_game_thread_queue)
            _UE_BRIDGE_TICK_KIND = "post"
        else:
            _UE_BRIDGE_TICK_KIND = "none"

    if _LAST_SELECTED_MATERIAL_PATH:
        message = f"UE Bridge started at http://{host}:{port} (cached selection: {_LAST_SELECTED_MATERIAL_PATH})"
    else:
        message = f"UE Bridge started at http://{host}:{port} (no cached selection)"
    unreal.log(message)
    return {"ok": True, "message": message}


def ensure_bridge(host: str = "127.0.0.1", port: int = 30010) -> dict:
    """Ensure UE bridge is running without forcing restart."""
    return start_bridge(host=host, port=port)


_UE_BRIDGE_GLOBALS["ensure_bridge"] = ensure_bridge


def stop_bridge() -> dict:
    global _UE_BRIDGE_SERVER, _UE_BRIDGE_TICK_HANDLE, _UE_BRIDGE_TICK_KIND

    try:
        _UE_BRIDGE_SERVER.shutdown()
        _UE_BRIDGE_SERVER.server_close()
        unregister_pre = getattr(unreal, "unregister_slate_pre_tick_callback", None)
        unregister_post = getattr(unreal, "unregister_slate_post_tick_callback", None)
        if _UE_BRIDGE_TICK_HANDLE is not None:
            if _UE_BRIDGE_TICK_KIND == "pre" and callable(unregister_pre):
                unregister_pre(_UE_BRIDGE_TICK_HANDLE)
            elif _UE_BRIDGE_TICK_KIND == "post" and callable(unregister_post):
                unregister_post(_UE_BRIDGE_TICK_HANDLE)
            elif callable(unregister_pre):
                try:
                    unregister_pre(_UE_BRIDGE_TICK_HANDLE)
                except Exception:
                    pass
                if callable(unregister_post):
                    try:
                        unregister_post(_UE_BRIDGE_TICK_HANDLE)
                    except Exception:
                        pass
            _UE_BRIDGE_TICK_HANDLE = None
            _UE_BRIDGE_TICK_KIND = ""
        unreal.log("UE Bridge stopped")
        return {"ok": True}
    except Exception:
        return {"ok": False, "message": "Bridge is not running"}


_UE_BRIDGE_SERVER = None
_UE_BRIDGE_THREAD = None
