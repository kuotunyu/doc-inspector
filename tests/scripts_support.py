"""Load executable scripts for isolated offline unit tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def load_script_module(name: str) -> ModuleType:
    path = Path(__file__).parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"doc_inspector_script_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"無法載入 script：{name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
