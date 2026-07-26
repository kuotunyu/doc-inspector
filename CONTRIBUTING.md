# 參與貢獻

感謝你願意改善 `doc-inspector`。這個專案以正體中文使用者體驗、可解釋規則、隱私與可重現驗證為優先。

## 開始前

- 請先搜尋既有 Issues，避免重複。
- Bug 請提供最小重現步驟；不要附上真實個資、API key 或完整雲端回應。
- 新 schema、外部服務、資料保存或會增加付費 API 用量的變更，請先開 Issue 說明需求與風險。

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
