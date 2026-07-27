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
PUBLIC_ASSET_DIR = ROOT / "docs" / "assets"
DEFAULT_AUDIT_OUTPUT_DIR = ROOT / "outputs" / "ui-audit"
AUDIT_OUTPUT_DIR = Path(
    os.environ.get("UI_TEST_OUTPUT_DIR", DEFAULT_AUDIT_OUTPUT_DIR)
)
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
            fontWeight: style.fontWeight,
            lineHeight: style.lineHeight,
            borderTopWidth: style.borderTopWidth
          };
        }"""
    )


def _all_metrics(locator: Locator) -> list[dict[str, float | str]]:
    return locator.evaluate_all(
        """elements => elements.map(element => {
          const box = element.getBoundingClientRect();
          const style = window.getComputedStyle(element);
          return {
            x: Math.round(box.x),
            y: Math.round(box.y),
            width: Math.round(box.width),
            height: Math.round(box.height),
            fontSize: style.fontSize,
            fontWeight: style.fontWeight,
            lineHeight: style.lineHeight,
            borderTopWidth: style.borderTopWidth
          };
        })"""
    )


def _dropdown_metrics(page: Page) -> dict:
    combo = page.locator("#demo-selector [role='combobox']").first
    combo.click()
    listbox = page.locator('#demo-selector [role="listbox"]').first
    option = page.locator(
        '#demo-selector [role="listbox"] [role="option"]'
    ).first
    option.wait_for(state="visible")
    metrics = {
        "control": _metrics(combo),
        "listbox": _metrics(listbox),
        "option": _metrics(option),
        "frontmostRole": option.evaluate(
            """element => {
              const box = element.getBoundingClientRect();
              return document.elementFromPoint(
                box.left + 16,
                box.top + box.height / 2
              )?.getAttribute("role") ?? "";
            }"""
        ),
    }
    page.keyboard.press("Escape")
    return metrics


def _page_metrics(page: Page) -> dict:
    dropdown = _dropdown_metrics(page)
    metrics = {
        "viewportWidth": page.evaluate("window.innerWidth"),
        "documentWidth": page.evaluate("document.documentElement.scrollWidth"),
        "documentHeight": page.evaluate("document.documentElement.scrollHeight"),
        "header": _metrics(page.locator(".app-header").first),
        "h1": _metrics(page.locator(".app-header h1").first),
        "bodyText": _metrics(page.locator(".app-header p").first),
        "masthead": _metrics(page.locator(".masthead").first),
        "resultLegend": _metrics(page.locator(".result-legend").first),
        "legendTitle": _metrics(page.locator(".result-legend h2").first),
        "legendItem": _metrics(page.locator(".legend-items li").first),
        "legendCards": _all_metrics(page.locator(".legend-items li")),
        "legendLabel": _metrics(page.locator(".legend-items strong").first),
        "legendAction": _metrics(page.locator(".legend-action").first),
        "legendDots": _all_metrics(page.locator(".legend-dot")),
        "sourceHeading": _metrics(page.locator(".source-brief h3").first),
        "sourceText": _metrics(page.locator(".source-brief p").first),
        "demoHeading": _metrics(page.locator(".demo-heading h3").first),
        "demoText": _metrics(page.locator(".demo-heading p").first),
        "demoDropdownControl": dropdown["control"],
        "demoDropdownListbox": dropdown["listbox"],
        "demoDropdownOption": dropdown["option"],
        "demoDropdownFrontmostRole": dropdown["frontmostRole"],
        "demoSelectorAccessible": page.get_by_label("範例文件").is_visible(),
        "documentPickerLabelVisible": page.locator(
            "#document-upload"
        ).get_by_text(
            "選擇申請表、收據或發票", exact=True
        ).is_visible(),
        "workbench": _metrics(page.locator(".workbench").first),
        "uploadPanel": _metrics(page.locator(".upload-section").first),
        "sourceBrief": _metrics(page.locator(".source-brief").first),
        "uploadControl": _metrics(page.locator(".upload-control").first),
        "uploadPrompt": _metrics(
            page.locator(".upload-control > button > .wrap").first
        ),
        "settingsPanel": _metrics(page.locator(".settings-section").first),
        "actionPanel": _metrics(page.locator(".action-section").first),
        "taskHeading": _metrics(page.locator(".task-heading").first),
        "stepMarkers": _all_metrics(page.locator(".task-step")),
        "taskTitle": _metrics(page.locator(".task-heading h2").first),
        "taskCopy": _metrics(page.locator(".task-heading p").first),
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
    upload = metrics["uploadControl"]
    prompt = metrics["uploadPrompt"]
    metrics["uploadPromptInsetTop"] = prompt["y"] - upload["y"]
    metrics["uploadPromptInsetBottom"] = (
        upload["y"] + upload["height"] - prompt["y"] - prompt["height"]
    )
    return metrics


def _theme_contrast(browser, color_scheme: str) -> dict:
    """Measure rendered text contrast under a browser color preference."""

    context = browser.new_context(
        viewport={"width": 1440, "height": 1000},
        color_scheme=color_scheme,
    )
    page = context.new_page()
    page.goto(URL, wait_until="networkidle")
    page.get_by_text("結果燈號", exact=True).wait_for(state="visible")
    selectors = (
        ".source-brief p",
        ".upload-guidance span",
        "#document-upload button .wrap",
        "#demo-selector input",
        "#schema-selector input",
        ".privacy-note p",
        ".task-heading p",
    )
    samples = {}
    for selector in selectors:
        samples[selector] = page.locator(selector).first.evaluate(
            """element => {
              const canvas = document.createElement("canvas");
              canvas.width = 1;
              canvas.height = 1;
              const context = canvas.getContext("2d", {willReadFrequently: true});
              const parseColor = value => {
                context.clearRect(0, 0, 1, 1);
                context.fillStyle = "rgba(0, 0, 0, 0)";
                context.fillStyle = value;
                context.fillRect(0, 0, 1, 1);
                const [red, green, blue, alpha] = context.getImageData(
                  0, 0, 1, 1
                ).data;
                return [red, green, blue, alpha / 255];
              };
              const composite = (front, back) => {
                const alpha = front[3] + back[3] * (1 - front[3]);
                if (alpha === 0) return [0, 0, 0, 0];
                return [
                  (front[0] * front[3]
                    + back[0] * back[3] * (1 - front[3])) / alpha,
                  (front[1] * front[3]
                    + back[1] * back[3] * (1 - front[3])) / alpha,
                  (front[2] * front[3]
                    + back[2] * back[3] * (1 - front[3])) / alpha,
                  alpha
                ];
              };
              const layers = [];
              let current = element;
              while (current) {
                const background = parseColor(
                  getComputedStyle(current).backgroundColor
                );
                if (background[3] > 0) layers.push(background);
                current = current.parentElement;
              }
              let background = [255, 255, 255, 1];
              for (const layer of layers.reverse()) {
                background = composite(layer, background);
              }
              const foreground = composite(
                parseColor(getComputedStyle(element).color),
                background
              );
              const luminance = color => {
                const channels = color.slice(0, 3).map(channel => {
                  const value = channel / 255;
                  return value <= 0.04045
                    ? value / 12.92
                    : ((value + 0.055) / 1.055) ** 2.4;
                });
                return (
                  0.2126 * channels[0]
                  + 0.7152 * channels[1]
                  + 0.0722 * channels[2]
                );
              };
              const foregroundLuminance = luminance(foreground);
              const backgroundLuminance = luminance(background);
              const ratio = (
                Math.max(foregroundLuminance, backgroundLuminance) + 0.05
              ) / (
                Math.min(foregroundLuminance, backgroundLuminance) + 0.05
              );
              return {
                color: getComputedStyle(element).color,
                backgroundColor: `rgb(${background.slice(0, 3)
                  .map(Math.round).join(", ")})`,
                contrastRatio: Math.round(ratio * 100) / 100
              };
            }"""
        )
    container_theme = page.locator(".gradio-container").first.evaluate(
        """element => {
          const style = getComputedStyle(element);
          return {
            browserPrefersDark: matchMedia(
              "(prefers-color-scheme: dark)"
            ).matches,
            renderedColorScheme: style.colorScheme,
            bodyTextColor: style.getPropertyValue("--body-text-color").trim(),
            inputBackground: style.getPropertyValue(
              "--input-background-fill"
            ).trim()
          };
        }"""
    )
    result = {
        "requestedColorScheme": color_scheme,
        "theme": container_theme,
        "samples": samples,
        "minimumContrastRatio": min(
            sample["contrastRatio"] for sample in samples.values()
        ),
    }
    context.close()
    return result


def _capture(
    browser,
    *,
    width: int,
    height: int,
    filename: str,
    output_dir: Path,
    console_errors: list[str],
    page_errors: list[str],
) -> tuple[dict, bool]:
    context = browser.new_context(
        viewport={"width": width, "height": height},
        color_scheme="light",
    )
    page = context.new_page()
    page.on(
        "console",
        lambda message: console_errors.append(message.text)
        if message.type == "error"
        else None,
    )
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.goto(URL, wait_until="networkidle")
    page.get_by_text("結果燈號", exact=True).wait_for(state="visible")
    page.get_by_text(
        "完成後照顏色處理", exact=True
    ).wait_for(state="visible")
    for label in [
        "送件前先修正",
        "對照原文件確認",
        "目前未發現問題",
    ]:
        page.get_by_text(label, exact=False).wait_for(state="visible")
    for step in [
        "準備要檢查的文件",
        "確認預檢設定",
        "確認傳送並開始",
        "查看預檢結果",
    ]:
        page.get_by_text(step, exact=True).wait_for(state="visible")
    page.get_by_text("文件從哪裡來？", exact=True).wait_for(state="visible")
    page.get_by_text("請上傳已填好的申請表", exact=False).wait_for(
        state="visible"
    )
    page.get_by_text("沒有文件？", exact=True).wait_for(state="visible")
    page.get_by_text("尚未產生修正建議", exact=True).wait_for(state="visible")
    page.screenshot(path=output_dir / filename, full_page=True)
    metrics = _page_metrics(page)
    consent_unchecked = not page.locator("#cloud-consent input").is_checked()
    context.close()
    return metrics, consent_unchecked


def _verify_consent_gate(
    browser,
    console_errors: list[str],
    page_errors: list[str],
) -> tuple[bool, bool, bool]:
    context = browser.new_context(
        viewport={"width": 1280, "height": 900},
        color_scheme="light",
    )
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
        ".action-section .status-output .status-card.status-red"
    ).is_visible()
    button_reenabled = page.locator(".primary-btn").is_enabled()
    context.close()
    return visible, status_near_action, button_reenabled


def _verify_demo_loader(
    browser,
    console_errors: list[str],
    page_errors: list[str],
) -> tuple[bool, bool, bool]:
    context = browser.new_context(
        viewport={"width": 1280, "height": 1000},
        color_scheme="light",
    )
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
    output_dir: Path,
) -> tuple[bool, bool, bool, bool]:
    context = browser.new_context(
        viewport={"width": 1440, "height": 1000},
        color_scheme="light",
    )
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
    page.screenshot(path=output_dir / "result-red.png", full_page=True)
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
    PUBLIC_ASSET_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    console_errors: list[str] = []
    page_errors: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        wide, wide_unchecked = _capture(
            browser,
            width=1920,
            height=1080,
            filename="wide.png",
            output_dir=AUDIT_OUTPUT_DIR,
            console_errors=console_errors,
            page_errors=page_errors,
        )
        desktop, desktop_unchecked = _capture(
            browser,
            width=1440,
            height=1000,
            filename="desktop.png",
            output_dir=PUBLIC_ASSET_DIR,
            console_errors=console_errors,
            page_errors=page_errors,
        )
        mobile, mobile_unchecked = _capture(
            browser,
            width=390,
            height=844,
            filename="mobile.png",
            output_dir=AUDIT_OUTPUT_DIR,
            console_errors=console_errors,
            page_errors=page_errors,
        )
        light_theme_contrast = _theme_contrast(browser, "light")
        dark_preference_contrast = _theme_contrast(browser, "dark")
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
                AUDIT_OUTPUT_DIR,
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
        "theme_contrast": {
            "light": light_theme_contrast,
            "dark_system_preference": dark_preference_contrast,
        },
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
    (AUDIT_OUTPUT_DIR / "browser-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    desktop_step_x = [marker["x"] for marker in desktop["stepMarkers"]]
    mobile_step_x = [marker["x"] for marker in mobile["stepMarkers"]]
    desktop_dot_widths = [dot["width"] for dot in desktop["legendDots"]]
    desktop_dot_heights = [dot["height"] for dot in desktop["legendDots"]]
    mobile_dot_widths = [dot["width"] for dot in mobile["legendDots"]]
    mobile_dot_heights = [dot["height"] for dot in mobile["legendDots"]]

    for viewport_name, metrics in (
        ("wide", wide),
        ("desktop", desktop),
        ("mobile", mobile),
    ):
        legend_cards = metrics["legendCards"]
        assert len(legend_cards) == 3, (
            f"{viewport_name} viewport should render exactly three legend cards"
        )
        legend_widths = [card["width"] for card in legend_cards]
        legend_heights = [card["height"] for card in legend_cards]
        assert max(legend_widths) - min(legend_widths) <= 1, (
            f"{viewport_name} legend cards should have equal widths: {legend_widths}"
        )
        assert max(legend_heights) - min(legend_heights) <= 1, (
            f"{viewport_name} legend cards should have equal heights: {legend_heights}"
        )

    assert desktop["viewportWidth"] == desktop["documentWidth"]
    assert mobile["viewportWidth"] == mobile["documentWidth"]
    assert float(desktop["bodyText"]["fontSize"].removesuffix("px")) >= 20
    assert float(desktop["legendTitle"]["fontSize"].removesuffix("px")) >= 22
    assert float(desktop["legendItem"]["fontSize"].removesuffix("px")) >= 18
    assert float(desktop["legendLabel"]["fontSize"].removesuffix("px")) >= 22
    assert float(desktop["legendAction"]["fontSize"].removesuffix("px")) >= 20
    assert len(desktop["legendDots"]) == 3
    assert desktop_dot_widths == [18, 18, 18]
    assert desktop_dot_heights == [18, 18, 18]
    assert float(desktop["sourceText"]["fontSize"].removesuffix("px")) >= 19
    assert float(desktop["demoText"]["fontSize"].removesuffix("px")) >= 18
    assert (
        float(desktop["demoDropdownControl"]["fontSize"].removesuffix("px"))
        >= 21
    )
    assert (
        float(desktop["demoDropdownOption"]["fontSize"].removesuffix("px"))
        >= 20
    )
    assert desktop["demoDropdownOption"]["height"] >= 44
    assert (
        desktop["demoDropdownListbox"]["y"]
        >= desktop["demoDropdownControl"]["y"]
        + desktop["demoDropdownControl"]["height"]
    )
    assert desktop["demoDropdownFrontmostRole"] == "option"
    assert len(desktop["stepMarkers"]) == 4
    assert all(marker["width"] >= 46 for marker in desktop["stepMarkers"])
    assert all(marker["height"] >= 46 for marker in desktop["stepMarkers"])
    assert max(desktop_step_x) - min(desktop_step_x) <= 1
    assert float(desktop["taskTitle"]["fontSize"].removesuffix("px")) >= 28
    assert float(desktop["taskCopy"]["fontSize"].removesuffix("px")) >= 20
    assert float(desktop["fieldLabel"]["fontSize"].removesuffix("px")) >= 18
    assert (
        float(desktop["uploadGuidance"]["fontSize"].removesuffix("px")) >= 18
    )
    assert float(desktop["primaryButton"]["fontSize"].removesuffix("px")) >= 20
    assert float(desktop["statusText"]["fontSize"].removesuffix("px")) >= 19
    assert float(mobile["bodyText"]["fontSize"].removesuffix("px")) >= 19
    assert float(mobile["legendItem"]["fontSize"].removesuffix("px")) >= 18
    assert float(mobile["legendLabel"]["fontSize"].removesuffix("px")) >= 21
    assert float(mobile["legendAction"]["fontSize"].removesuffix("px")) >= 19
    assert len(mobile["legendDots"]) == 3
    assert mobile_dot_widths == [18, 18, 18]
    assert mobile_dot_heights == [18, 18, 18]
    assert float(mobile["sourceText"]["fontSize"].removesuffix("px")) >= 19
    assert (
        float(mobile["demoDropdownOption"]["fontSize"].removesuffix("px"))
        >= 20
    )
    assert mobile["demoDropdownOption"]["height"] >= 44
    assert (
        mobile["demoDropdownListbox"]["y"]
        >= mobile["demoDropdownControl"]["y"]
        + mobile["demoDropdownControl"]["height"]
    )
    assert mobile["demoDropdownFrontmostRole"] == "option"
    assert len(mobile["stepMarkers"]) == 4
    assert all(marker["width"] >= 46 for marker in mobile["stepMarkers"])
    assert all(marker["height"] >= 46 for marker in mobile["stepMarkers"])
    assert max(mobile_step_x) - min(mobile_step_x) <= 1
    assert float(mobile["fieldLabel"]["fontSize"].removesuffix("px")) >= 18
    assert desktop["masthead"]["height"] <= 150
    assert desktop["resultLegend"]["height"] <= 140
    assert desktop["uploadPanel"]["height"] <= 480
    assert desktop["noticeGrid"]["height"] <= 180
    assert desktop["actionGrid"]["height"] <= 110
    assert desktop["workbench"]["y"] <= 225
    assert desktop["uploadPromptInsetTop"] >= 6
    assert desktop["uploadPromptInsetBottom"] >= 6
    assert desktop["documentHeight"] <= 1900
    assert (
        float(
            desktop["settingsPanel"]["borderTopWidth"].removesuffix("px")
        )
        >= 8
    )
    assert (
        float(desktop["actionPanel"]["borderTopWidth"].removesuffix("px"))
        >= 8
    )
    assert (
        abs(
            desktop["settingsPanel"]["y"]
            - (
                desktop["uploadPanel"]["y"]
                + desktop["uploadPanel"]["height"]
            )
        )
        <= 2
    )
    assert (
        abs(
            desktop["actionPanel"]["y"]
            - (
                desktop["settingsPanel"]["y"]
                + desktop["settingsPanel"]["height"]
            )
        )
        <= 2
    )
    assert mobile["resultLegend"]["height"] <= 180
    assert mobile["masthead"]["height"] <= 340
    assert mobile["workbench"]["y"] <= 410
    assert mobile["workbench"]["width"] / mobile["viewportWidth"] >= 0.9
    assert mobile["uploadPromptInsetTop"] >= 6
    assert mobile["uploadPromptInsetBottom"] >= 6
    assert mobile["documentHeight"] <= 2900
    assert "尚未執行預檢" in desktop["emptyResultHint"]
    assert desktop["resultTabs"]["height"] >= 130
    assert desktop["demoSelectorAccessible"]
    assert mobile["demoSelectorAccessible"]
    assert desktop["documentPickerLabelVisible"]
    assert mobile["documentPickerLabelVisible"]
    assert not light_theme_contrast["theme"]["browserPrefersDark"]
    assert dark_preference_contrast["theme"]["browserPrefersDark"]
    assert light_theme_contrast["theme"]["renderedColorScheme"] == "light"
    assert dark_preference_contrast["theme"]["renderedColorScheme"] == "light"
    for preference in (light_theme_contrast, dark_preference_contrast):
        assert preference["minimumContrastRatio"] >= 4.5
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
