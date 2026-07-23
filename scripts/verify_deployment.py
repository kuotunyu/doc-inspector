"""Static, secret-safe verification for the CPU deployment bundle."""

from __future__ import annotations

import json
from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    base_dependencies = project["project"]["dependencies"]
    retrieval_dependencies = project["project"]["optional-dependencies"]["local-retrieval"]
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    ui_source = (ROOT / "src" / "doc_inspector" / "ui.py").read_text(
        encoding="utf-8"
    )

    forbidden_base = ("torch", "transformers", "accelerate")
    assert not any(dependency.startswith(forbidden_base) for dependency in base_dependencies)
    assert any(dependency.startswith("torch") for dependency in retrieval_dependencies)
    assert "uv sync --locked --no-dev --no-editable" in dockerfile
    assert "GRADIO_SERVER_NAME=0.0.0.0" in dockerfile
    assert "GRADIO_TEMP_DIR=/tmp/doc-inspector-gradio" in dockerfile
    assert "GRADIO_ANALYTICS_ENABLED=False" in dockerfile
    assert "PUBLIC_MAX_REQUESTS_PER_HOUR=60" in dockerfile
    assert "USER appuser" in dockerfile
    assert 'api_visibility="private"' in ui_source
    assert "max_size=8" in ui_source
    assert "analytics_enabled=False" in ui_source
    assert "enable_monitoring=False" in ui_source
    assert "allowed_paths=" not in ui_source
    assert ".env" in dockerignore
    assert "data/" in dockerignore
    assert "*.safetensors" in dockerignore

    summary = {
        "base_dependency_count": len(base_dependencies),
        "local_retrieval_dependency_count": len(retrieval_dependencies),
        "cpu_image_excludes_local_retrieval": True,
        "secret_files_excluded": True,
        "non_root_runtime": True,
        "managed_temp_cleanup": True,
        "analytics_disabled": True,
        "event_api_private": True,
        "bounded_queue": True,
        "monitoring_disabled": True,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
