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

## 已知且刻意未修的相依警示

以下兩項已評估並**刻意暫不升級**。兩者都只出現在可選的 `local-retrieval` GPU extra；
base 安裝、GitHub Actions CI 與公開 CPU 容器都不包含它們。

| 套件 | 等級 | 問題 | 為什麼暫不升級 |
|---|---|---|---|
| `torch` 2.11.0+cu128 | low | `torch.jit.script` 記憶體毀損 | 專案不呼叫 `torch.jit.script`；視覺檢索走 Transformers 原生實作與 SDPA。已修補版 2.13.0 在專案固定使用的 cu128 index 上不存在（cp311 最新為 2.11.0），升級等同更換 CUDA channel。 |
| `setuptools` 81.0.0 | medium | sdist 在 macOS APFS/HFS+ 的 MANIFEST.in 排除繞過（Unicode NFC/NFD 碰撞） | 由 `torch` 的 metadata 連帶約束，torch 不動就無法單獨升到 83.0.0。發布包只在 Windows 與 Ubuntu 建置，不觸及 macOS 檔案系統的正規化行為。 |

**重新評估條件**：cu128（或後續採用的 CUDA channel）出現 torch 2.13 以上版本時一併升級，
並重跑 GPU 視覺檢索評估、更新 README 記錄的實測環境與數字。在那之前，README 上的
ColQwen2 結果對應的是已驗證的 Torch 2.11.0+cu128 環境。

這兩項在 `.github/dependabot.yml` 以 `ignore` 標註，避免 Dependabot 重複產生無法完成的更新任務。

## 維護者檢查

```powershell
uv lock --check
uv run pytest
uv run python scripts/verify_release.py
```

公開 repository 建議另外啟用 GitHub Secret scanning、Push protection、Dependabot security updates 與 CodeQL default setup。
