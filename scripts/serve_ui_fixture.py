"""Serve deterministic synthetic UI fixtures without loading dotenv or models."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from tempfile import gettempdir

from doc_inspector.demo import (
    PROVENANCE_DEMO_NAME,
    demo_extractions,
    generate_demo_artifacts,
    provenance_demo_extraction,
)
from doc_inspector.ingest import normalize_document
from doc_inspector.provenance import resolve_provenance
from doc_inspector.rules import inspect_extraction
from doc_inspector.schemas import InspectionBundle
from doc_inspector.service import InspectionArtifacts
from doc_inspector.types import ProviderName, SchemaName
from doc_inspector.ui import (
    CIVIC_CSS,
    CIVIC_THEME,
    build_app,
    ensure_local_port_available,
    prepare_gradio_temp_root,
)


DEFAULT_PORT = 7862


def fixture_inspector(
    path: Path,
    schema: SchemaName,
    provider: ProviderName,
) -> InspectionArtifacts:
    """Return the named synthetic fixture without network or credential access.

    Extraction is replayed from a fixed synthetic answer, but ingestion and
    provenance resolution run for real, so the browser gate exercises the same
    local verification path the product uses.
    """

    del schema
    source = Path(path)
    key = source.stem
    if key == PROVENANCE_DEMO_NAME:
        extraction = provenance_demo_extraction()
    else:
        fixtures = demo_extractions()
        if key not in fixtures:
            raise ValueError(f"離線 UI fixture 不支援：{key}。")
        extraction = fixtures[key]

    document = normalize_document(source)
    bundle = InspectionBundle(
        provider=provider,
        model="offline-ui-fixture",
        source_file_name=source.name,
        page_count=len(document.pages),
        elapsed_ms=0,
        extraction=extraction,
        review_report=inspect_extraction(extraction),
        provenance=resolve_provenance(
            extraction,
            document.text_layer,
            pages=document.pages,
        ),
    )
    return InspectionArtifacts(bundle=bundle, pages=document.pages)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="啟動不讀 .env、不呼叫模型的 UI 測試 fixture。",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--temp-dir",
        type=Path,
        default=Path(gettempdir()) / f"doc-inspector-ui-fixture-{DEFAULT_PORT}",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if not 1 <= args.port <= 65535:
        raise ValueError("port 必須介於 1 與 65535。")
    temp_dir = args.temp_dir.expanduser().resolve()
    os.environ["GRADIO_TEMP_DIR"] = str(temp_dir)
    root = prepare_gradio_temp_root()
    generate_demo_artifacts(root / "demo")
    ensure_local_port_available(args.port)
    print(
        f"offline UI fixture: http://127.0.0.1:{args.port} "
        "（不讀 .env、不呼叫模型）"
    )
    build_app(inspector=fixture_inspector).launch(
        server_name="127.0.0.1",
        server_port=args.port,
        share=False,
        theme=CIVIC_THEME,
        css=CIVIC_CSS,
        show_error=False,
        max_file_size=25 * 1024 * 1024,
        max_threads=4,
        state_session_capacity=200,
        enable_monitoring=False,
    )


if __name__ == "__main__":
    main()
