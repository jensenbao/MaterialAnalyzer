"""UE-side helper script for opening the Streamlit analyzer from selected material.

Usage in Unreal Python console:

import ue_open_web_for_selected_material as launcher
launcher.open_web_for_selected_material()

You can bind this function to a plugin button/menu action.
"""

from __future__ import annotations

from urllib.parse import quote

import unreal
import ue_http_bridge_server as bridge

from material_analyzer_runtime import STREAMLIT_URL, ensure_streamlit_server, open_url


def _get_selected_material_asset_path() -> str:
    assets = unreal.EditorUtilityLibrary.get_selected_assets()
    for asset in assets:
        if isinstance(asset, unreal.Material):
            return asset.get_path_name()
    raise RuntimeError("No Material selected in Content Browser")


def open_web_for_selected_material(web_url: str = STREAMLIT_URL) -> dict:
    bridge_state = bridge.ensure_bridge()
    streamlit_state = ensure_streamlit_server(show_progress=False, wait_timeout_seconds=0.0)
    material_path = _get_selected_material_asset_path()
    target_url = f"{web_url}?material_name={quote(material_path, safe='')}"
    opened = open_url(target_url)
    return {
        "ok": bool(opened),
        "bridge": bridge_state,
        "streamlit": streamlit_state,
        "material_path": material_path,
        "url": target_url,
        "opened": bool(opened),
    }


def open_web_home(web_url: str = STREAMLIT_URL) -> dict:
    bridge_state = bridge.ensure_bridge()
    streamlit_state = ensure_streamlit_server(show_progress=False, wait_timeout_seconds=0.0)
    opened = open_url(web_url)
    return {
        "ok": bool(opened),
        "bridge": bridge_state,
        "streamlit": streamlit_state,
        "url": web_url,
        "opened": bool(opened),
    }
