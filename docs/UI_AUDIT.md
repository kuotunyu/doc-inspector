# UI 技術品質稽核

> 日期：2026-07-26
> 範圍：本機 Gradio 介面、補助綠／黃／紅與收據綠結果、1920×1080、1440×1000、390×844、light／dark 系統偏好
> 方法：Playwright 離線 fixture、DOM／鍵盤／尺寸／實際文字對比與 CSS 檢查；未呼叫模型 API

## Audit Health Score

| # | Dimension | Baseline | 修正後 | Key Finding |
|---|---:|---:|---:|---|
| 1 | Accessibility | 3/4 | 4/4 | 控制皆有名稱；鍵盤可到達語意表格，所有焦點皆可見 |
| 2 | Performance | 4/4 | 4/4 | 本機 DCL 21 ms、load 35 ms、transfer 261,911 bytes |
| 3 | Responsive Design | 3/4 | 4/4 | 390 px 無全頁溢位；必要表格只在自身區域橫向捲動 |
| 4 | Theming | 2/4 | 3/4 | light／dark token 已成對固定；少量狀態色仍待逐步收斂 |
| 5 | Anti-Patterns | 3/4 | 4/4 | 移除 Dataframe 虛假操作與結果分頁的大模糊陰影 |
| **Total** |  | **15/20** | **19/20** | **Excellent — 核心可用性與系統偏好問題已修正** |

## Executive Summary

- 修正前：P0 0、P1 2、P2 2、P3 2。
- 修正後：P0 0、P1 0、P2 0、P3 1；唯一保留項目是逐步收斂 CSS 硬編碼顏色。
- 桌機與手機皆為 `lang="zh-TW"`、單一 main landmark、連續標題層級、無重複 ID。
- `unnamedInteractive`、`undersizedInteractive`、`focusWithoutVisibleIndicator` 均為 0；390 px `mobileHorizontalOverflow=false`。
- 補助綠／黃／紅與收據綠四種結果皆提供白話下一步與操作方式，不把工程欄位路徑暴露給一般使用者。
- 瀏覽器 light／dark 系統偏好下，七個關鍵文字區塊最低對比皆為 6.89:1，高於 WCAG AA 正文門檻 4.5:1。

## 已解決問題

### [Resolved P1] 手機結果分頁的無名稱三點選單

將第三個分頁縮短為「JSON」，三個分頁可直接顯示；不再產生無可存取名稱的溢位選單。

### [Resolved P1] 結果表格沒有可見鍵盤焦點

唯讀 Gradio Dataframe 已改為具 caption、欄標題 scope、命名 region 與 `tabindex="0"` 的語意表格；region 取得焦點時顯示 3 px 高對比外框。

### [Resolved P1] 深色系統偏好造成淺色介面文字低對比

Gradio 的 dark token 原本會在瀏覽器偏好深色時把部分文字切成淺色，但自訂表面仍維持淺色。正式 app 與離線 fixture 現在共用同一個 `CIVIC_THEME`，light／dark token 成對指向已驗收的淺色 civic palette；Playwright 會分別模擬兩種偏好並以 4.5:1 為最低 gate。

### [Resolved P2] 隱藏分頁按鈕進入鍵盤順序

Gradio 產生的 `.tab-container.visually-hidden` 已移出版面；稽核焦點順序只包含三個可見分頁。

### [Resolved P2] 次要表格控制小於 44 px

Dataframe 的 24×24 工具列與 27 px 欄名按鈕已移除。唯讀結果不再顯示複製、全螢幕、排序或編輯 affordance；所有保留的互動目標皆達專案 44 px 基準。

### [Resolved P3] 結果分頁 ghost-card 陰影

保留 1 px 邊界並移除 16 px 模糊陰影，讓行動清單維持第一視覺優先。

## 保留項目

### [P3] 表面與狀態色仍混用硬編碼值

- Location：`CIVIC_CSS` 內少量 hover、processing、表格與狀態色。
- Impact：目前對比與狀態均正確，但未來換主題時可能漏改。
- Recommendation：後續只在實際調整相關區塊時收斂至既有 `--ui-*` token，不為抽象而大規模重寫。

## Positive Findings

- 鍵盤可依序到達上傳、範例、設定、同意、主要按鈕、三個結果分頁、結果表格 region 與兩個下載按鈕。
- 最新自動對比抽查涵蓋來源說明、上傳指引、上傳控制、兩個 selector、隱私告知與步驟文字；light／dark 系統偏好最低皆為 6.89:1。
- 唯讀表格內容在輸出前經 HTML escaping；`<script>` 與 `<img onerror>` 測試字串只會顯示成文字。
- 所有離線案例 console error 0、page error 0。

## Verification

- `uv run pytest tests/test_ui.py tests/test_ui_fixture.py -q` → 20 passed。
- `uv run --all-extras pytest --cov=doc_inspector --cov-report=term-missing -q` → 148 passed、coverage 89%。
- `uv lock --check` → 通過。
- `uv run python -m compileall -q src tests scripts` → 通過。
- PowerShell 終端 A：`uv run python scripts/serve_ui_fixture.py --port 7862`。
- PowerShell 終端 B：`$env:UI_TEST_URL = 'http://127.0.0.1:7862'; $env:UI_TEST_EXPECT_ACTION_PLAN = '1'; uv run python scripts/verify_ui_layout.py`。
- PowerShell 終端 B：`uv run python scripts/audit_ui_quality.py` → unnamed 0、undersized 0、focusWithoutVisibleIndicator 0、mobile overflow false。
- 兩個稽核腳本預設只接受 `127.0.0.1:7862`，避免誤將自動測試送到 7861 真實 provider app；fixture 不讀 `.env`、不呼叫模型。
- 完整機器可讀報告：`docs/assets/ui-quality-audit.json`；responsive、互動與 light／dark 對比證據另見 `docs/assets/browser-report.json`。
