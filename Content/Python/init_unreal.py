"""Plugin auto-start entry.

Delegates to material_analyzer_init.py so the plugin works without project-level wrappers.
"""

from __future__ import annotations

import importlib.util
import os


_THIS_DIR = os.path.dirname(__file__)
_INIT_FILE = os.path.join(_THIS_DIR, "material_analyzer_init.py")

if not os.path.exists(_INIT_FILE):
    raise RuntimeError(f"MaterialAnalyzer init not found: {_INIT_FILE}")

_spec = importlib.util.spec_from_file_location("material_analyzer_plugin_init_direct", _INIT_FILE)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"Failed to load MaterialAnalyzer init spec: {_INIT_FILE}")

_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
