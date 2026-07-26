# Security Policy

## 支援範圍

目前安全修正以預設分支及最新公開版本為主。舊 commit 不保證回補。

## 回報安全問題

請使用 GitHub repository 的 **Private vulnerability reporting**。不要在公開 Issue 貼出：

- API key、token 或 `.env` 內容。
- 真實身分資料、申請文件、收據或未去識別附件。
- 可直接利用的完整攻擊步驟。
- 雲端 provider 的 raw response。

回報時請包含受影響版本、最小重現方式、可能影響與建議修正。維護者確認前，請保留合理的協調揭露時間。

若 repository 尚未啟用 Private vulnerability reporting，請只建立一個不含漏洞細節的公開 Issue，請維護者提供私下回報管道。

## 安全與隱私邊界

- API key 只從環境變數讀取，不得提交到 Git 或放在 client-side code。
- 文件只在暫存目錄處理，完成或失敗後清除。
- Log 不應記錄文件內容、個資或完整 provider response。
- JSON／Excel 匯出不得含本機絕對路徑或 raw API response。
- 公開 demo 會把文件傳給使用者選定的雲端 provider；介面必須先取得明確同意。
- 程序內 rate limit 不是完整的 per-user、跨重啟防護；公開部署仍需供應商後台支出上限。
- 工具只做技術預檢，不提供資格或法律判斷。

## 維護者檢查

```powershell
uv lock --check
uv run pytest
uv run python scripts/verify_release.py
```

公開 repository 建議另外啟用 GitHub Secret scanning、Push protection、Dependabot security updates 與 CodeQL default setup。
