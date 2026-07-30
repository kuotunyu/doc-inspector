"""Public orchestration service for one-document inspection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Protocol

from doc_inspector.config import AppSettings, load_settings
from doc_inspector.ingest import NormalizedDocument, NormalizedPage, normalize_document
from doc_inspector.ocr import load_evidence_ocr_provider
from doc_inspector.providers import ExtractionResult, LangChainStructuredExtractor
from doc_inspector.provenance import resolve_provenance
from doc_inspector.rules import inspect_extraction
from doc_inspector.schemas import InspectionBundle, SchemaRegistry
from doc_inspector.types import ProviderName, SchemaName


class DocumentExtractor(Protocol):
    """Minimal dependency-injection boundary used by offline tests."""

    def extract(
        self,
        document: NormalizedDocument,
        schema: SchemaName,
        provider: ProviderName,
    ) -> ExtractionResult: ...


@dataclass(frozen=True, slots=True)
class InspectionArtifacts:
    """An inspection plus the in-memory pages needed to show verified evidence.

    ``bundle`` stays free of image bytes and local paths so it can be exported
    as-is; ``pages`` never leaves the process except as an on-demand preview.
    """

    bundle: InspectionBundle
    pages: tuple[NormalizedPage, ...]


def _inspect_document(
    path: Path,
    schema: SchemaName,
    provider: ProviderName,
    *,
    settings: AppSettings | None = None,
    extractor: DocumentExtractor | None = None,
) -> InspectionArtifacts:
    """Normalize, extract, validate, and package one document without persisting its contents."""

    SchemaRegistry.get(schema)
    active_settings = settings or load_settings()
    start = perf_counter()

    normalized = normalize_document(
        Path(path),
        max_file_bytes=active_settings.max_file_bytes,
        max_pdf_pages=active_settings.max_pdf_pages,
        render_dpi=active_settings.render_dpi,
        max_long_edge=active_settings.max_image_long_edge,
    )
    active_extractor = extractor or LangChainStructuredExtractor(active_settings)
    result = active_extractor.extract(normalized, schema, provider)
    provenance = resolve_provenance(
        result.parsed,
        normalized.text_layer,
        pages=normalized.pages,
        ocr_provider=load_evidence_ocr_provider(
            enabled=active_settings.evidence_ocr_enabled,
            languages=active_settings.evidence_ocr_languages,
        ),
    )
    elapsed_ms = max(0, round((perf_counter() - start) * 1000))

    warnings = [*result.warnings, *result.parsed.extraction_warnings]
    bundle = InspectionBundle(
        provider=result.provider,
        model=result.model,
        source_file_name=normalized.source_file_name,
        page_count=len(normalized.pages),
        elapsed_ms=elapsed_ms,
        usage=result.usage,
        extraction=result.parsed,
        warnings=warnings,
        review_report=inspect_extraction(result.parsed),
        provenance=provenance,
    )
    return InspectionArtifacts(bundle=bundle, pages=normalized.pages)


def inspect_document_detailed(
    path: Path,
    schema: SchemaName,
    provider: ProviderName,
) -> InspectionArtifacts:
    """Inspect one local document and keep its rendered pages for evidence preview."""

    return _inspect_document(path, schema, provider)


def inspect_document(
    path: Path,
    schema: SchemaName,
    provider: ProviderName,
) -> InspectionBundle:
    """Public fixed interface for inspecting one local document."""

    return _inspect_document(path, schema, provider).bundle
