"""Load executable scripts for isolated offline unit tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType


def load_script_module(name: str) -> ModuleType:
    path = Path(__file__).parents[1] / "scripts" / f"{name}.py"
    module_name = f"doc_inspector_script_{name}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"無法載入 script：{name}")
    module = importlib.util.module_from_spec(spec)
    # Registering before execution lets dataclasses resolve the postponed
    # annotations that `from __future__ import annotations` leaves as strings.
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    return module
