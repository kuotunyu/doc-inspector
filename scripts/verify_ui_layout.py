"""Capture responsive UI evidence and fail on basic layout regressions."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from tempfile import gettempdir
from urllib.parse import urlsplit

from playwright.sync_api import Locator, Page, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "docs" / "assets"
URL = os.environ.get("UI_TEST_URL", "http://127.0.0.1:7862")
VERIFY_ACTION_PLAN = os.environ.get("UI_TEST_EXPECT_ACTION_PLAN") == "1"
DEMO_DIR = Path(
    os.environ.get(
        "UI_TEST_DEMO_DIR",
        Path(gettempdir()) / "doc-inspector-ui-fixture-7862" / "demo",
    )
)


def validate_test_target(url: str, *, allow_non_fixture: bool = False) -> None:
    """Refuse to aim an automated UI test at the normal app by accident."""

    if allow_non_fixture:
        return
    parsed = urlsplit(url)
    if parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.port != 7862:
        raise RuntimeError(
            "UI 稽核預設只允許 127.0.0.1:7862 離線 fixture；"
            "若確定要測其他目標，請顯式設定 UI_TEST_ALLOW_NON_FIXTURE=1。"
        )


def _metrics(locator: Locator) -> dict[str, float | str]:
    return locator.evaluate(
        """element => {
          const box = element.getBoundingClientRect();
          const style = window.getComputedStyle(element);
          return {
            x: Math.round(box.x),
            y: Math.round(box.y),
            width: Math.round(box.width),
            height: Math.round(box.height),
            fontSize: style.fontSize,
            lineHeight: style.lineHeight
          };
        }"""
    )


def _page_metrics(page: Page) -> dict:
    return {
        "viewportWidth": page.evaluate("window.innerWidth"),
        "documentWidth": page.evaluate("document.documentElement.scrollWidth"),
        "header": _metrics(page.locator(".app-header").first),
        "h1": _metrics(page.locator(".app-header h1").first),
        "bodyText": _metrics(page.locator(".app-header p").first),
        "masthead": _metrics(page.locator(".masthead").first),
        "workflowGuide": _metrics(page.locator(".workflow-guide").first),
        "workflowTitle": _metrics(page.locator(".workflow-guide h2").first),
        "workflowStepTitle": _metrics(
            page.locator(".workflow-copy strong").first
        ),
        "workflowStepCopy": _metrics(page.locator(".workflow-copy p").first),
        "sourceHeading": _metrics(page.locator(".source-brief h3").first),
        "sourceText": _metrics(page.locator(".source-brief p").first),
        "demoHeading": _metrics(page.locator(".demo-heading h3").first),
        "demoText": _metrics(page.locator(".demo-heading p").first),
        "demoSelectorAccessible": page.get_by_label("範例文件").is_visible(),
        "documentPickerLabelVisible": page.locator(
            "#document-upload"
        ).get_by_text(
            "選擇申請表、收據或發票", exact=True
        ).is_visible(),
        "workbench": _metrics(page.locator(".workbench").first),
        "uploadPanel": _metrics(page.locator(".upload-section").first),
        "settingsPanel": _metrics(page.locator(".settings-section").first),
        "sectionHeading": _metrics(page.locator(".section-heading h2").first),
        "sectionCopy": _metrics(page.locator(".section-heading p").first),
        "fieldLabel": _metrics(
            page.locator('#schema-selector [data-testid="block-info"]').first
        ),
        "uploadGuidance": _metrics(page.locator(".upload-guidance").first),
        "noticeGrid": _metrics(page.locator(".notice-grid").first),
        "privacyText": _metrics(page.locator(".privacy-note p").first),
        "actionGrid": _metrics(page.locator(".action-grid").first),
        "primaryButton": _metrics(page.locator(".primary-btn").first),
        "statusText": _metrics(page.locator(".status-card").first),
        "actionPlan": _metrics(page.locator(".action-plan").first),
        "resultTabs": _metrics(page.locator(".result-tabs").first),
        "emptyResultHint": page.locator(
            "#extraction-table .result-empty"
        ).inner_text(),
        "layoutAncestors": page.locator(".app-header").first.evaluate(
            """element => {
              const ancestors = [];
              let current = element.parentElement;
              while (current && ancestors.length < 10) {
                const box = current.getBoundingClientRect();
                const style = window.getComputedStyle(current);
                ancestors.push({
                  tag: current.tagName,
                  id: current.id,
                  className: current.className,
                  width: Math.round(box.width),
                  paddingLeft: style.paddingLeft,
                  paddingRight: style.paddingRight
                });
                current = current.parentElement;
              }
              return ancestors;
            }"""
        ),
    }


def _capture(
    browser,
    *,
    width: int,
    height: int,
    filename: str,
    console_errors: list[str],
    page_errors: list[str],
) -> tuple[dict, bool]:
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    page.on(
        "console",
        lambda message: console_errors.append(message.text)
        if message.type == "error"
        else None,
    )
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.goto(URL, wait_until="networkidle")
    page.get_by_text("照這 4 步完成預檢", exact=True).wait_for(state="visible")
    for step in ["準備文件", "確認設定", "同意並開始", "查看結果"]:
        page.get_by_text(step, exact=True).wait_for(state="visible")
    page.get_by_text("去哪裡取得？", exact=True).wait_for(state="visible")
    page.get_by_text("請選填好的申請表或店家收據／發票", exact=False).wait_for(
        state="visible"
    )
    page.get_by_text("沒有文件？", exact=True).wait_for(state="visible")
    page.get_by_text("尚未產生修正建議", exact=True).wait_for(state="visible")
    page.screenshot(path=ASSET_DIR / filename, full_page=True)
    metrics = _page_metrics(page)
    consent_unchecked = not page.locator("#cloud-consent input").is_checked()
    context.close()
    return metrics, consent_unchecked


def _verify_consent_gate(
    browser,
    console_errors: list[str],
    page_errors: list[str],
) -> tuple[bool, bool, bool]:
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page.on(
        "console",
        lambda message: console_errors.append(message.text)
        if message.type == "error"
        else None,
    )
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.goto(URL, wait_until="networkidle")
    page.locator(".primary-btn").click()
    error = page.get_by_text("請先勾選雲端傳送告知", exact=False)
    error.wait_for(state="visible")
    visible = error.is_visible()
    status_near_action = page.locator(
        ".settings-section .status-output .status-card.status-red"
    ).is_visible()
    button_reenabled = page.locator(".primary-btn").is_enabled()
    context.close()
    return visible, status_near_action, button_reenabled


def _verify_demo_loader(
    browser,
    console_errors: list[str],
    page_errors: list[str],
) -> tuple[bool, bool, bool]:
    context = browser.new_context(viewport={"width": 1280, "height": 1000})
    page = context.new_page()
    page.on(
        "console",
        lambda message: console_errors.append(message.text)
        if message.type == "error"
        else None,
    )
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.goto(URL, wait_until="networkidle")
    page.locator("#load-demo").click()
    loaded = page.get_by_text("已載入安全範例：", exact=False)
    loaded.wait_for(state="visible", timeout=30_000)
    file_visible = page.locator(
        '#document-upload [aria-label="receipt_green.png"]'
    ).is_visible()
    status_visible = loaded.is_visible()
    schema_updated = (
        page.locator("#schema-selector input").input_value() == "收據／發票"
    )
    context.close()
    return file_visible, status_visible, schema_updated


def _verify_actionable_result(
    browser,
    console_errors: list[str],
    page_errors: list[str],
) -> tuple[bool, bool, bool, bool]:
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    page.on(
        "console",
        lambda message: console_errors.append(message.text)
        if message.type == "error"
        else None,
    )
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.goto(URL, wait_until="networkidle")
    red_demo_path = DEMO_DIR / "subsidy_red.png"
    page.locator('#document-upload input[type="file"]').set_input_files(
        red_demo_path
    )
    page.get_by_text("subsidy_red.png", exact=True).wait_for(state="visible")
    page.locator("#cloud-consent input").check()
    page.locator(".primary-btn").click()
    page.get_by_text("先修正 4 項", exact=False).wait_for(
        state="visible",
        timeout=30_000,
    )
    page.get_by_text("查看修正建議 ↓", exact=True).click()
    action_plan_visible = page.get_by_text(
        "先照這份清單處理", exact=True
    ).is_visible()
    next_step_visible = page.get_by_text(
        "回到上方換上修正後的文件", exact=False
    ).is_visible()
    plain_language_visible = page.get_by_text(
        "逐字核對身分證字號", exact=False
    ).is_visible()
    machine_paths_hidden = page.locator("#action-plan").get_by_text(
        "applicants.0", exact=False
    ).count() == 0
    page.screenshot(path=ASSET_DIR / "result-red.png", full_page=True)
    context.close()
    return (
        action_plan_visible,
        next_step_visible,
        plain_language_visible,
        machine_paths_hidden,
    )


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    validate_test_target(
        URL,
        allow_non_fixture=os.environ.get("UI_TEST_ALLOW_NON_FIXTURE") == "1",
    )
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    console_errors: list[str] = []
    page_errors: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        wide, wide_unchecked = _capture(
            browser,
            width=1920,
            height=1080,
            filename="wide.png",
            console_errors=console_errors,
            page_errors=page_errors,
        )
        desktop, desktop_unchecked = _capture(
            browser,
            width=1440,
            height=1000,
            filename="desktop.png",
            console_errors=console_errors,
            page_errors=page_errors,
        )
        mobile, mobile_unchecked = _capture(
            browser,
            width=390,
            height=844,
            filename="mobile.png",
            console_errors=console_errors,
            page_errors=page_errors,
        )
        (
            consent_error_visible,
            status_near_action,
            button_reenabled_after_error,
        ) = _verify_consent_gate(
            browser,
            console_errors,
            page_errors,
        )
        demo_file_visible, demo_status_visible, demo_schema_updated = _verify_demo_loader(
            browser,
            console_errors,
            page_errors,
        )
        if VERIFY_ACTION_PLAN:
            (
                action_plan_visible,
                next_step_visible,
                plain_language_visible,
                machine_paths_hidden,
            ) = _verify_actionable_result(
                browser,
                console_errors,
                page_errors,
            )
        else:
            action_plan_visible = None
            next_step_visible = None
            plain_language_visible = None
            machine_paths_hidden = None
        browser.close()

    report = {
        "url": URL,
        "screenshots": [
            "wide.png",
            "desktop.png",
            "mobile.png",
            *(["result-red.png"] if VERIFY_ACTION_PLAN else []),
        ],
        "wide_metrics": wide,
        "desktop_metrics": desktop,
        "mobile_metrics": mobile,
        "consent_control_default_unchecked": (
            wide_unchecked and desktop_unchecked and mobile_unchecked
        ),
        "consent_error_visible_before_api_call": consent_error_visible,
        "persistent_status_near_action": status_near_action,
        "button_reenabled_after_error": button_reenabled_after_error,
        "demo_file_loaded_without_api": demo_file_visible,
        "demo_status_visible": demo_status_visible,
        "demo_schema_updated": demo_schema_updated,
        "action_plan_checked": VERIFY_ACTION_PLAN,
        "action_plan_visible": action_plan_visible,
        "action_plan_next_step_visible": next_step_visible,
        "action_plan_plain_language_visible": plain_language_visible,
        "action_plan_machine_paths_hidden": machine_paths_hidden,
        "console_errors": console_errors,
        "page_errors": page_errors,
    }
    (ASSET_DIR / "browser-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    assert desktop["viewportWidth"] == desktop["documentWidth"]
    assert mobile["viewportWidth"] == mobile["documentWidth"]
    assert float(desktop["bodyText"]["fontSize"].removesuffix("px")) >= 18
    assert float(desktop["workflowTitle"]["fontSize"].removesuffix("px")) >= 21
    assert (
        float(desktop["workflowStepTitle"]["fontSize"].removesuffix("px"))
        >= 19
    )
    assert (
        float(desktop["workflowStepCopy"]["fontSize"].removesuffix("px"))
        >= 17
    )
    assert float(desktop["sourceText"]["fontSize"].removesuffix("px")) >= 17
    assert float(desktop["demoText"]["fontSize"].removesuffix("px")) >= 17
    assert float(desktop["sectionHeading"]["fontSize"].removesuffix("px")) >= 24
    assert float(desktop["sectionCopy"]["fontSize"].removesuffix("px")) >= 18
    assert float(desktop["fieldLabel"]["fontSize"].removesuffix("px")) >= 17
    assert (
        float(desktop["uploadGuidance"]["fontSize"].removesuffix("px")) >= 17
    )
    assert float(desktop["primaryButton"]["fontSize"].removesuffix("px")) >= 18
    assert float(desktop["statusText"]["fontSize"].removesuffix("px")) >= 18
    assert float(mobile["bodyText"]["fontSize"].removesuffix("px")) >= 17
    assert (
        float(mobile["workflowStepCopy"]["fontSize"].removesuffix("px")) >= 17
    )
    assert float(mobile["sourceText"]["fontSize"].removesuffix("px")) >= 17
    assert float(mobile["fieldLabel"]["fontSize"].removesuffix("px")) >= 17
    assert desktop["workflowStepCopy"]["height"] <= 30
    assert desktop["masthead"]["height"] <= 170
    assert desktop["noticeGrid"]["height"] <= 180
    assert desktop["actionGrid"]["height"] <= 100
    assert desktop["workbench"]["y"] <= 340
    assert desktop["workbench"]["height"] <= 650
    assert mobile["workflowGuide"]["height"] <= 270
    assert mobile["masthead"]["height"] <= 390
    assert mobile["workbench"]["y"] <= 520
    assert mobile["workbench"]["width"] / mobile["viewportWidth"] >= 0.9
    assert "尚未執行預檢" in desktop["emptyResultHint"]
    assert desktop["resultTabs"]["height"] >= 130
    assert desktop["demoSelectorAccessible"]
    assert mobile["demoSelectorAccessible"]
    assert desktop["documentPickerLabelVisible"]
    assert mobile["documentPickerLabelVisible"]
    assert report["consent_control_default_unchecked"]
    assert report["consent_error_visible_before_api_call"]
    assert report["persistent_status_near_action"]
    assert report["button_reenabled_after_error"]
    assert report["demo_file_loaded_without_api"]
    assert report["demo_status_visible"]
    assert report["demo_schema_updated"]
    if VERIFY_ACTION_PLAN:
        assert report["action_plan_visible"]
        assert report["action_plan_next_step_visible"]
        assert report["action_plan_plain_language_visible"]
        assert report["action_plan_machine_paths_hidden"]
    assert not console_errors
    assert not page_errors
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
