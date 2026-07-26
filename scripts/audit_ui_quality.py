"""Audit measurable accessibility, responsive, and result-state UI behavior."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from tempfile import gettempdir
from urllib.parse import urlsplit

from playwright.sync_api import Page, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT_OUTPUT_DIR = ROOT / "outputs" / "ui-audit"
AUDIT_OUTPUT_DIR = Path(
    os.environ.get("UI_TEST_OUTPUT_DIR", DEFAULT_AUDIT_OUTPUT_DIR)
)
REPORT_PATH = AUDIT_OUTPUT_DIR / "ui-quality-audit.json"
URL = os.environ.get("UI_TEST_URL", "http://127.0.0.1:7862")
DEMO_DIR = Path(
    os.environ.get(
        "UI_TEST_DEMO_DIR",
        Path(gettempdir()) / "doc-inspector-ui-fixture-7862" / "demo",
    )
)


def validate_test_target(url: str, *, allow_non_fixture: bool = False) -> None:
    """Refuse to aim an automated result audit at a real provider-backed app."""

    if allow_non_fixture:
        return
    parsed = urlsplit(url)
    if parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.port != 7862:
        raise RuntimeError(
            "UI 稽核預設只允許 127.0.0.1:7862 離線 fixture；"
            "若確定要測其他目標，請顯式設定 UI_TEST_ALLOW_NON_FIXTURE=1。"
        )


def _dom_scan(page: Page) -> dict:
    return page.evaluate(
        """() => {
          const visible = element => {
            const style = getComputedStyle(element);
            const box = element.getBoundingClientRect();
            return style.visibility !== "hidden"
              && style.display !== "none"
              && box.width > 0
              && box.height > 0;
          };
          const nameOf = element => {
            const labelledBy = element.getAttribute("aria-labelledby");
            if (labelledBy) {
              return labelledBy.split(/\\s+/)
                .map(id => document.getElementById(id)?.textContent || "")
                .join(" ")
                .trim();
            }
            const labels = element.labels
              ? [...element.labels].map(label => label.textContent || "").join(" ")
              : "";
            return (
              element.getAttribute("aria-label")
              || labels
              || element.getAttribute("title")
              || element.textContent
              || element.getAttribute("value")
              || ""
            ).trim().replace(/\\s+/g, " ");
          };
          const interactiveSelector = [
            "a[href]",
            "button",
            "input:not([type=hidden])",
            "select",
            "textarea",
            "[role=button]",
            "[role=checkbox]",
            "[role=combobox]",
            "[role=tab]"
          ].join(",");
          const interactive = [...document.querySelectorAll(interactiveSelector)]
            .filter(visible)
            .map(element => {
              const target = element instanceof HTMLInputElement
                && element.type === "checkbox"
                && element.labels?.length
                ? element.labels[0]
                : element;
              const box = target.getBoundingClientRect();
              return {
                tag: element.tagName.toLowerCase(),
                role: element.getAttribute("role") || "",
                name: nameOf(element),
                className: String(element.className || ""),
                parentClasses: [
                  element.parentElement?.className || "",
                  element.parentElement?.parentElement?.className || ""
                ].map(value => String(value)),
                ariaLabel: element.getAttribute("aria-label") || "",
                width: Math.round(box.width),
                height: Math.round(box.height),
                html: element.outerHTML.slice(0, 500)
              };
            });
          const ids = [...document.querySelectorAll("[id]")]
            .map(element => element.id)
            .filter(Boolean);
          const duplicates = [...new Set(ids.filter(
            (id, index) => ids.indexOf(id) !== index
          ))];
          const headings = [...document.querySelectorAll("h1,h2,h3,h4,h5,h6")]
            .filter(visible)
            .map(element => ({
              level: Number(element.tagName.slice(1)),
              text: (element.textContent || "").trim().replace(/\\s+/g, " ")
            }));
          const headingSkips = headings.slice(1).filter(
            (heading, index) => heading.level > headings[index].level + 1
          );
          return {
            title: document.title,
            lang: document.documentElement.lang,
            mainLandmarks: document.querySelectorAll("main,[role=main]").length,
            headings,
            headingSkips,
            duplicateIds: duplicates,
            interactiveCount: interactive.length,
            unnamedInteractive: interactive.filter(item => !item.name),
            undersizedInteractive: interactive.filter(
              item => item.width < 44 || item.height < 44
            )
          };
        }"""
    )


def _focus_scan(page: Page, limit: int = 24) -> list[dict]:
    page.evaluate(
        """() => {
          if (document.activeElement instanceof HTMLElement) {
            document.activeElement.blur();
          }
        }"""
    )
    items = []
    seen: set[tuple[str, str, str]] = set()
    for _ in range(limit):
        page.keyboard.press("Tab")
        item = page.evaluate(
            """() => {
              const element = document.activeElement;
              if (!(element instanceof HTMLElement)) return null;
              const style = getComputedStyle(element);
              const box = element.getBoundingClientRect();
              const labels = element.labels
                ? [...element.labels].map(label => label.textContent || "").join(" ")
                : "";
              const name = (
                element.getAttribute("aria-label")
                || labels
                || element.getAttribute("title")
                || element.textContent
                || element.getAttribute("value")
                || ""
              ).trim().replace(/\\s+/g, " ");
              const outlineVisible = style.outlineStyle !== "none"
                && parseFloat(style.outlineWidth || "0") > 0;
              const shadowVisible = style.boxShadow !== "none";
              return {
                tag: element.tagName.toLowerCase(),
                role: element.getAttribute("role") || "",
                name,
                className: String(element.className || ""),
                top: Math.round(box.top),
                outline: style.outline,
                boxShadow: style.boxShadow,
                focusVisible: outlineVisible || shadowVisible
              };
            }"""
        )
        if not item or item["tag"] == "body":
            break
        signature = (item["tag"], item["role"], item["name"])
        if signature in seen:
            break
        seen.add(signature)
        items.append(item)
    return items


def _performance_scan(page: Page) -> dict:
    return page.evaluate(
        """() => {
          const navigation = performance.getEntriesByType("navigation")[0];
          const resources = performance.getEntriesByType("resource");
          return {
            domContentLoadedMs: Math.round(
              navigation.domContentLoadedEventEnd - navigation.startTime
            ),
            loadMs: Math.round(navigation.loadEventEnd - navigation.startTime),
            resourceCount: resources.length,
            transferBytes: Math.round(resources.reduce(
              (total, entry) => total + (entry.transferSize || 0),
              0
            ))
          };
        }"""
    )


def _result_case(browser, key: str, expected_level: str) -> dict:
    context = browser.new_context(
        viewport={"width": 1440, "height": 1000},
        color_scheme="light",
    )
    page = context.new_page()
    console_errors: list[str] = []
    page_errors: list[str] = []
    page.on(
        "console",
        lambda message: console_errors.append(message.text)
        if message.type == "error"
        else None,
    )
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.goto(URL, wait_until="networkidle")
    demo_path = DEMO_DIR / f"{key}.png"
    page.locator('#document-upload input[type="file"]').set_input_files(
        demo_path
    )
    page.get_by_text(demo_path.name, exact=True).wait_for(state="visible")
    page.locator("#cloud-consent input").check()
    page.locator(".primary-btn").click()
    status = page.locator(f".status-card.status-{expected_level}")
    status.wait_for(state="visible", timeout=30_000)
    action_plan = page.locator("#action-plan")
    action_plan_text = action_plan.inner_text()
    result = {
        "level": expected_level,
        "statusText": status.inner_text(),
        "actionPlanText": action_plan_text,
        "hasNextStep": "下一步" in status.inner_text(),
        "hasActionInstruction": (
            "怎麼處理" in action_plan_text
            if expected_level != "green"
            else "人工確認" in action_plan_text
        ),
        "machinePathVisible": any(
            marker in action_plan_text
            for marker in ("applicants.", "line_items.", "required.", "amount.")
        ),
        "consoleErrors": console_errors,
        "pageErrors": page_errors,
    }
    context.close()
    return result


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    validate_test_target(
        URL,
        allow_non_fixture=os.environ.get("UI_TEST_ALLOW_NON_FIXTURE") == "1",
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        desktop_context = browser.new_context(
            viewport={"width": 1440, "height": 1000},
            color_scheme="light",
        )
        desktop_page = desktop_context.new_page()
        desktop_page.goto(URL, wait_until="networkidle")
        desktop = _dom_scan(desktop_page)
        focus = _focus_scan(desktop_page)
        performance = _performance_scan(desktop_page)
        desktop_context.close()

        mobile_context = browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=2,
            has_touch=True,
            color_scheme="light",
        )
        mobile_page = mobile_context.new_page()
        mobile_page.goto(URL, wait_until="networkidle")
        mobile = _dom_scan(mobile_page)
        mobile_overflow = mobile_page.evaluate(
            "document.documentElement.scrollWidth > window.innerWidth"
        )
        mobile_context.close()

        result_cases = {
            "subsidy_green": _result_case(browser, "subsidy_green", "green"),
            "subsidy_yellow": _result_case(browser, "subsidy_yellow", "yellow"),
            "subsidy_red": _result_case(browser, "subsidy_red", "red"),
            "receipt_green": _result_case(browser, "receipt_green", "green"),
        }
        browser.close()

    report = {
        "url": URL,
        "desktop": desktop,
        "mobile": mobile,
        "mobileHorizontalOverflow": mobile_overflow,
        "focusSequence": focus,
        "focusWithoutVisibleIndicator": [
            item for item in focus if not item["focusVisible"]
        ],
        "performance": performance,
        "resultCases": result_cases,
    }
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
