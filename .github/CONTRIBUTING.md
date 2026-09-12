# 參與貢獻

感謝你願意改善 `doc-inspector`。這個專案以正體中文使用者體驗、可解釋規則、隱私與可重現驗證為優先。

## 維護範圍與重啟條件

自 2026-09-10 起，本專案維持 **v1.1.3 feature freeze／必要維護模式**。這是保留可展示的既有作品，不是停止安全維護，也不代表已驗證真實案件的 production readiness。此政策適用於人工與 AI 協作；舊的強化計畫或 prompt 不構成新的開工授權。

- **可進行的維護**：有重現證據的功能／部署故障、安全問題、必要相依相容性修正，以及影響理解的事實錯誤。修正範圍應與問題相稱。
- **預設不進行**：例行換模型或調 prompt、追求 XFUND 分數、增加 schema／OCR／裁切流程、擴張評測、重新美化介面，以及沒有新問題的反覆收尾或發布整理。剩餘工具額度不是重啟理由。
- **重新開發的條件**：維護者明確選定實際使用者與目標文件的需求，或決定以 Document AI／OCR 為核心求職方向，並同意一個有資料來源、驗收標準與停止條件的新里程碑。符合候選條件不代表自動批准開工。
- **評測邊界**：XFUND 使用獨立的通用 key-value benchmark 路徑；其分數不等於補助申請／收據兩個固定 schema 的端到端品質。不能僅憑該分數判定產品需要救援，也不能把 benchmark 改善直接宣稱為實際案件改善。
- **保留基線**：未批准新里程碑前，不修改既有模型選型、凍結資料、歷史評測或 release tags，不因文件維護觸發付費評測、GPU 工作、HF 重部署或新版本發布。

開始任何工作前先查目前分支、未提交變更、近期提交及此節政策。若沒有符合範圍的問題，回報維持現狀即可，不必另開收尾任務或新增結案文件。後續明確批准的新工作可以取代這項預設，但須保留其與既有發布基線的區別。

## 開始前

- 請先搜尋既有 Issues，避免重複。
- Bug 請提供最小重現步驟；不要附上真實個資、API key 或完整雲端回應。
- 新 schema、外部服務、資料保存或會增加付費 API 用量的變更，須先依上述重啟條件取得維護者同意；提出 Issue 本身不代表批准開發。

## 本機環境

需求：Windows 11 或 Ubuntu、Python 3.11、[uv](https://docs.astral.sh/uv/)。

```powershell
uv sync --all-groups
uv run pytest
```

如需 optional GPU 頁面檢索：

```powershell
uv sync --all-extras --all-groups
uv run --all-extras pytest
```

基本測試不需要 `.env`、API key、GPU、Tesseract 或網路。

## 修改原則

1. 模型只負責抽取；可確定的行政、日期、身分與金額判斷放在純函式規則。
2. 新欄位必須有 Pydantic schema、來源頁碼與短證據 contract。
3. 不保存 raw API response、真實文件或本機絕對路徑。
4. Provider、模型 ID 與 token 上限必須可設定，不得寫死秘密。
5. 公開文案以正體中文為主，technical terms 保留原文。
6. Windows 與 Linux 路徑使用 `pathlib.Path`。
7. 新功能需附 pytest；修正 bug 時先加入能重現問題的測試。

## 送出 Pull Request 前

```powershell
uv lock --check
uv run pytest --cov=doc_inspector --cov-report=term --cov-fail-under=85
uv run python scripts/verify_deployment.py
uv run python -m compileall -q src scripts tests
uv run python scripts/run_product_evaluation.py --check
uv run python scripts/verify_public_docs.py
uv build --clear --no-build-isolation
uv run python scripts/verify_distribution.py
uv run python scripts/verify_release.py
```

Pull Request 請說明：

- 問題與使用者影響。
- 解法與取捨。
- 測試證據。
- 隱私、成本、相容性與 migration 影響。
- UI 變更的前後截圖（如適用）。

## Commit

採 Conventional Commits，主旨以正體中文為主：

```text
feat: 新增收據折扣一致性規則
fix: 修正缺少日期時的黃燈提示
docs: 補充決策層評估限制
test: 增加多頁 PDF 邊界案例
```
