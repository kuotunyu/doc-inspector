from __future__ import annotations

from pathlib import Path
import socket
from types import SimpleNamespace

import gradio as gr
import pytest

import doc_inspector.ui as ui_module
from doc_inspector.demo import demo_extractions
from doc_inspector.rules import inspect_extraction
from doc_inspector.schemas import InspectionBundle, LocatedValue, Receipt
from doc_inspector.ui import (
    build_app,
    ensure_local_port_available,
    gradio_temp_root,
    inspection_update_stream,
    load_demo_document_callback,
    prepare_gradio_temp_root,
    run_inspection_callback,
)


def fake_inspector(path: Path, schema: str, provider: str) -> InspectionBundle:
    receipt = Receipt(
        merchant_name=LocatedValue(value="測試商店", page_number=1),
        receipt_date=LocatedValue(value="2026-07-23", page_number=1),
        total=LocatedValue(value="100", page_number=1),
    )
    return InspectionBundle(
        provider=provider,
        model="mock-model",
        source_file_name=path.name,
        page_count=1,
        elapsed_ms=5,
        extraction=receipt,
        review_report=inspect_extraction(receipt),
    )


def red_demo_inspector(path: Path, schema: str, provider: str) -> InspectionBundle:
    extraction = demo_extractions()["subsidy_red"]
    return InspectionBundle(
        provider=provider,
        model="mock-model",
        source_file_name=path.name,
        page_count=1,
        elapsed_ms=5,
        extraction=extraction,
        review_report=inspect_extraction(extraction),
    )


def unsafe_table_inspector(
    path: Path,
    schema: str,
    provider: str,
) -> InspectionBundle:
    receipt = Receipt(
        merchant_name=LocatedValue(
            value="<script>alert(1)</script>",
            page_number=1,
            evidence_text='<img src=x onerror="alert(2)">',
        ),
        receipt_date=LocatedValue(value="2026-07-23", page_number=1),
        total=LocatedValue(value="100", page_number=1),
    )
    return InspectionBundle(
        provider=provider,
        model="mock-model",
        source_file_name=path.name,
        page_count=1,
        elapsed_ms=5,
        extraction=receipt,
        review_report=inspect_extraction(receipt),
    )


def test_callback_requires_explicit_cloud_consent(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="雲端傳送告知"):
        run_inspection_callback(
            "sample.png",
            "receipt",
            "openai",
            False,
            inspector=fake_inspector,
            export_root=tmp_path,
        )


def test_callback_checks_request_budget_before_calling_provider(tmp_path: Path) -> None:
    provider_called = False

    def guarded_inspector(
        path: Path,
        schema: str,
        provider: str,
    ) -> InspectionBundle:
        nonlocal provider_called
        provider_called = True
        return fake_inspector(path, schema, provider)

    def exhausted_guard() -> None:
        raise ValueError("公開測試版目前已達每小時 60 次的共用上限。")

    with pytest.raises(ValueError, match="共用上限"):
        run_inspection_callback(
            "sample.png",
            "receipt",
            "openai",
            True,
            inspector=guarded_inspector,
            export_root=tmp_path,
            request_guard=exhausted_guard,
        )

    assert provider_called is False


def test_callback_returns_tables_and_downloads_without_absolute_source_path(tmp_path: Path) -> None:
    source = tmp_path / "private.png"
    source.write_bytes(b"not-read-by-fake")

    (
        status,
        action_plan,
        extraction,
        checks,
        payload,
        json_path,
        excel_path,
        _view,
        _selector,
        _detail,
        _preview,
    ) = run_inspection_callback(
        str(source),
        "receipt",
        "openai",
        True,
        inspector=fake_inspector,
        export_root=tmp_path / "exports",
    )

    assert "先修正" in status
    assert "查看修正建議" in status
    assert "怎麼處理" in action_plan
    assert extraction
    assert ">店家名稱<" in extraction
    assert "merchant_name" not in extraction
    assert checks
    assert "required." not in checks
    assert "amount." not in checks
    assert payload["source_file_name"] == "private.png"
    assert str(tmp_path) not in str(payload)
    assert Path(json_path).is_file()
    assert Path(excel_path).is_file()


def test_callback_escapes_source_name_in_status_html(tmp_path: Path) -> None:
    status, *_ = run_inspection_callback(
        "unsafe<script>.png",
        "receipt",
        "openai",
        True,
        inspector=fake_inspector,
        export_root=tmp_path,
    )

    assert "<script>" not in status
    assert "unsafe&lt;script&gt;.png" in status


def test_callback_escapes_model_values_in_result_table(tmp_path: Path) -> None:
    _, _, extraction, *_ = run_inspection_callback(
        "unsafe.png",
        "receipt",
        "openai",
        True,
        inspector=unsafe_table_inspector,
        export_root=tmp_path,
    )

    assert "<script>" not in extraction
    assert "<img" not in extraction
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in extraction
    assert "&lt;img src=x onerror=&quot;alert(2)&quot;&gt;" in extraction


def test_inspection_stream_disables_button_then_reenables_it(
    tmp_path: Path,
) -> None:
    updates = list(
        inspection_update_stream(
            str(tmp_path / "sample.png"),
            "receipt",
            "openai",
            True,
            inspector=fake_inspector,
            export_root=tmp_path / "exports",
        )
    )

    assert len(updates) == 2
    assert all(len(update) == 12 for update in updates)
    assert "正在預檢" in updates[0][0]
    assert updates[0][-1]["interactive"] is False
    assert updates[0][-1]["value"] == "預檢進行中…"
    assert "查看修正建議" in updates[1][0]
    assert updates[1][-1]["interactive"] is True
    assert updates[1][-1]["value"] == "再次預檢"


def test_inspection_stream_keeps_validation_error_visible() -> None:
    updates = list(
        inspection_update_stream(
            None,
            "receipt",
            "openai",
            False,
            inspector=fake_inspector,
        )
    )

    assert len(updates) == 2
    assert "無法開始預檢" in updates[1][0]
    assert "雲端傳送告知" in updates[1][0]
    assert updates[1][-1]["interactive"] is True
    assert updates[1][-1]["value"] == "開始預檢"


def test_port_check_does_not_terminate_port_owner() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as owner:
        owner.bind(("127.0.0.1", 0))
        port = owner.getsockname()[1]
        with pytest.raises(RuntimeError, match="未終止"):
            ensure_local_port_available(port)


def test_build_app_does_not_launch_server() -> None:
    app = build_app()

    assert app is not None
    assert app.analytics_enabled is False
    assert app.api_open is False
    assert app._queue.max_size == 8
    dependencies = app.get_config_file()["dependencies"]
    assert dependencies
    assert all(item["api_visibility"] == "private" for item in dependencies)


def test_gradio_temp_root_is_shared_with_download_components(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = tmp_path / "managed-cache"
    monkeypatch.setenv("GRADIO_TEMP_DIR", str(configured))

    root = prepare_gradio_temp_root()
    app = build_app()
    download_buttons = [
        block for block in app.blocks.values() if isinstance(block, gr.DownloadButton)
    ]

    assert root == configured.resolve()
    assert root.is_dir()
    assert gradio_temp_root() == root
    assert download_buttons
    assert all(Path(button.GRADIO_CACHE) == root for button in download_buttons)


def test_gradio_temp_root_rejects_relative_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRADIO_TEMP_DIR", "relative-cache")

    with pytest.raises(RuntimeError, match="絕對路徑"):
        gradio_temp_root()


def test_launch_applies_public_resource_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launch_kwargs: dict[str, object] = {}

    class FakeApp:
        def launch(self, **kwargs: object) -> None:
            launch_kwargs.update(kwargs)

    settings = SimpleNamespace(
        gradio_server_port=7861,
        gradio_server_name="127.0.0.1",
        public_max_requests_per_hour=60,
        max_file_bytes=25 * 1024 * 1024,
    )
    monkeypatch.setenv("GRADIO_TEMP_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(ui_module, "load_settings", lambda: settings)
    monkeypatch.setattr(ui_module, "ensure_local_port_available", lambda *_: None)
    monkeypatch.setattr(ui_module, "build_app", lambda **_: FakeApp())

    ui_module.launch()

    assert launch_kwargs["max_file_size"] == 25 * 1024 * 1024
    assert launch_kwargs["max_threads"] == 4
    assert launch_kwargs["state_session_capacity"] == 200
    assert launch_kwargs["enable_monitoring"] is False
    assert launch_kwargs["theme"] is ui_module.CIVIC_THEME
    assert "allowed_paths" not in launch_kwargs


def test_civic_theme_keeps_light_and_dark_tokens_consistent() -> None:
    theme = ui_module.CIVIC_THEME.to_dict()["theme"]
    paired_tokens = (
        "body_background_fill",
        "body_text_color",
        "body_text_color_subdued",
        "background_fill_primary",
        "background_fill_secondary",
        "block_background_fill",
        "block_info_text_color",
        "block_label_text_color",
        "input_background_fill",
        "input_placeholder_color",
        "button_primary_background_fill",
        "button_secondary_background_fill",
        "button_secondary_text_color",
    )

    for token in paired_tokens:
        assert theme[token] == theme[f"{token}_dark"]


def test_civic_css_keeps_steps_and_dropdowns_readable() -> None:
    css = ui_module.CIVIC_CSS

    assert ".workflow-section + .workflow-section" in css
    assert "border-top: 10px solid var(--ui-bg)" in css
    assert "box-shadow: inset 0 2px 0 var(--ui-border)" in css
    assert "width: 18px" in css
    assert "min-width: 18px" in css
    assert "max-width: 18px" in css
    assert "flex: 0 0 18px" in css
    assert "font-size: 22px" in css
    assert '.gradio-container [role="listbox"] [role="option"]' in css
    assert "position: absolute !important" in css
    assert "top: calc(100% + 6px) !important" in css
    assert "bottom: auto !important" in css
    assert '.workflow-section:has([role="listbox"])' in css
    assert "min-height: 46px" in css
    assert "font-size: 20px" in css
    assert "width: 46px" in css
    assert "flex: 0 0 46px" in css
    assert "padding: 18px 28px 0" in css
    assert ".results-heading::before" not in css


def test_civic_css_keeps_legend_cards_equal_sized() -> None:
    css = ui_module.CIVIC_CSS

    assert "grid-auto-rows: 1fr" in css
    assert "align-items: stretch" in css
    assert "height: 100%" in css
    assert "align-self: stretch" in css


def test_load_demo_document_selects_file_and_matching_schema(tmp_path: Path) -> None:
    file_path, schema, status = load_demo_document_callback(
        "receipt_green",
        demo_root=tmp_path,
    )

    assert Path(file_path).is_file()
    assert Path(file_path).name == "receipt_green.png"
    assert schema == "receipt"
    assert "不含真實個資" in status


def test_load_demo_document_rejects_unknown_choice(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="請先選擇"):
        load_demo_document_callback("unknown", demo_root=tmp_path)


def test_red_demo_result_leads_with_plain_language_actions(tmp_path: Path) -> None:
    source = tmp_path / "subsidy_red.png"
    source.write_bytes(b"not-read-by-fake")

    status, action_plan, extraction, checks, *_ = run_inspection_callback(
        str(source),
        "subsidy_application",
        "gemini",
        True,
        inspector=red_demo_inspector,
        export_root=tmp_path / "exports",
    )

    assert "先修正 4 項" in status
    assert "1 項需要人工確認" in status
    assert "先照這份清單處理" in action_plan
    assert "申請日期" in action_plan
    assert "逐字核對身分證字號" in action_plan
    assert "重新加總每筆補助明細" in action_plan
    assert "明細加總：1300；申報總額：1200" in action_plan
    assert "application_date" not in action_plan
    assert "applicants.0" not in action_plan
    assert ">申請人 1／證件類型<" in extraction
    assert ">日期格式<" in checks
