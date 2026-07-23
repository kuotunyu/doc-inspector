from __future__ import annotations

from inspect import signature
from pathlib import Path

import pymupdf
from PIL import Image

from doc_inspector.config import AppSettings
from doc_inspector.ingest import NormalizedDocument
from doc_inspector.providers import ExtractionResult
from doc_inspector.schemas import LocatedValue, Receipt, SubsidyApplication, TokenUsage
from doc_inspector.service import _inspect_document, inspect_document
from doc_inspector.types import ProviderName, SchemaName


class FakeExtractor:
    def __init__(self, parsed: SubsidyApplication | Receipt) -> None:
        self.parsed = parsed
        self.received_document: NormalizedDocument | None = None

    def extract(
        self,
        document: NormalizedDocument,
        schema: SchemaName,
        provider: ProviderName,
    ) -> ExtractionResult:
        self.received_document = document
        return ExtractionResult(
            provider=provider,
            model="mock-model-from-config",
            parsed=self.parsed,
            usage=TokenUsage(input_tokens=8, output_tokens=2, total_tokens=10),
            warnings=("mock warning",),
        )


def offline_settings() -> AppSettings:
    return AppSettings(_env_file=None, render_dpi=72, max_image_long_edge=500)


def test_public_service_signature_is_fixed() -> None:
    assert tuple(signature(inspect_document).parameters) == ("path", "schema", "provider")


def test_inspect_single_image_returns_safe_bundle(tmp_path: Path) -> None:
    path = tmp_path / "private-source.png"
    Image.new("RGB", (64, 32), "white").save(path)
    parsed = SubsidyApplication(
        program_name=LocatedValue(value="測試補助", page_number=1, evidence_text="測試補助"),
        extraction_warnings=["欄位模糊"],
    )
    extractor = FakeExtractor(parsed)

    bundle = _inspect_document(
        path,
        "subsidy_application",
        "gemini",
        settings=offline_settings(),
        extractor=extractor,
    )

    assert bundle.source_file_name == path.name
    assert bundle.page_count == 1
    assert bundle.usage.total_tokens == 10
    assert bundle.warnings == ["mock warning", "欄位模糊"]
    assert bundle.review_report.status == "completed"
    assert bundle.review_report.overall_level == "red"
    assert str(tmp_path) not in bundle.model_dump_json()


def test_inspect_multipage_pdf_passes_all_pages_to_extractor(tmp_path: Path) -> None:
    path = tmp_path / "two-pages.pdf"
    document = pymupdf.open()
    document.new_page(width=100, height=100)
    document.new_page(width=100, height=100)
    document.save(path)
    document.close()
    extractor = FakeExtractor(Receipt())

    bundle = _inspect_document(
        path,
        "receipt",
        "openai",
        settings=offline_settings(),
        extractor=extractor,
    )

    assert bundle.page_count == 2
    assert extractor.received_document is not None
    assert [page.page_number for page in extractor.received_document.pages] == [1, 2]
    assert bundle.provider == "openai"
