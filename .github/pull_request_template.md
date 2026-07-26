## 問題與使用者影響

<!-- 這個變更解決什麼問題？誰會受益？ -->

## 解法與取捨

<!-- 說明設計、替代方案，以及刻意沒有做的事。 -->

## 驗證

- [ ] 新增或更新 pytest
- [ ] `uv lock --check`
- [ ] `uv run pytest --cov=doc_inspector --cov-fail-under=85`
- [ ] `uv run python scripts/verify_deployment.py`
- [ ] `uv run python -m compileall -q src scripts tests`
- [ ] `uv run python scripts/run_product_evaluation.py --check`
- [ ] `uv run python scripts/verify_public_docs.py`
- [ ] `uv build --clear --no-build-isolation`
- [ ] `uv run python scripts/verify_distribution.py`
- [ ] `uv run python scripts/verify_release.py`
- [ ] UI 變更附前後截圖（不適用可註明）

## 風險

- [ ] 不含 API key、個資、raw provider response 或本機絕對路徑
- [ ] 已說明成本與外部服務影響
- [ ] 已確認 Windows／Linux 相容性
- [ ] 已說明 schema、匯出格式或 migration 影響
