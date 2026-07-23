from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from doc_inspector.demo import DEMO_SEED, WATERMARK, demo_extractions, generate_demo_artifacts
from doc_inspector.rules import inspect_extraction


def test_demo_scenarios_cover_expected_levels() -> None:
    levels = {
        name: inspect_extraction(extraction).overall_level
        for name, extraction in demo_extractions().items()
    }

    assert levels == {
        "subsidy_green": "green",
        "subsidy_yellow": "yellow",
        "subsidy_red": "red",
        "receipt_green": "green",
    }


def test_generate_demo_artifacts_writes_safe_manifest_and_exports(tmp_path: Path) -> None:
    artifacts = generate_demo_artifacts(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["seed"] == DEMO_SEED
    assert manifest["watermark"] == WATERMARK
    assert manifest["contains_real_personal_data"] is False
    assert len(artifacts) == 4
    for artifact in artifacts:
        assert artifact.image_path.is_file()
        assert artifact.extraction_path.is_file()
        assert artifact.bundle_path.is_file()
        assert artifact.workbook_path.is_file()
        with Image.open(artifact.image_path) as image:
            assert image.size == (1600, 2200)
