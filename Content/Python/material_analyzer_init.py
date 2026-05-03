"""Project startup hook for MaterialAnalyzer plugin.

Auto-starts the lightweight bridge without prompting to open the web UI.
"""

from __future__ import annotations

import traceback

import unreal

from material_analyzer_runtime import STREAMLIT_URL, ensure_streamlit_server, open_url


_INIT_GUARD_ATTR = "_material_analyzer_plugin_init_done"
_SHOULD_RUN_INIT = not getattr(unreal, _INIT_GUARD_ATTR, False)
if _SHOULD_RUN_INIT:
    setattr(unreal, _INIT_GUARD_ATTR, True)
else:
    unreal.log("[MaterialAnalyzer] startup skipped (already initialized)")


def _autostart_bridge() -> None:
    try:
        import ue_http_bridge_server as bridge

        result = bridge.ensure_bridge()
        unreal.log(f"[MaterialAnalyzer] Bridge autostart: {result}")
    except Exception as exc:
        unreal.log_warning(f"[MaterialAnalyzer] Bridge autostart failed: {exc}")
        unreal.log_warning(traceback.format_exc())


if _SHOULD_RUN_INIT:
    _autostart_bridge()
