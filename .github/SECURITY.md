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

## 可選 GPU 依賴的安全維護

`local-retrieval` 使用官方 cu130 index 的 Torch 2.13，以及 setuptools 84.1 以上版本
（lockfile 固定為 84.2.1），解除舊 Torch 2.11 的 `setuptools<82` 約束。
這同時取代舊版 Torch 的 `torch.jit.script` 風險接受紀錄，以及舊 setuptools 的 macOS
MANIFEST 排除繞過紀錄。setuptools 的新 Windows legacy wheel 安裝路徑問題
[GHSA-xmj3-9gf7-h52w](https://github.com/pypa/setuptools/security/advisories/GHSA-xmj3-9gf7-h52w)
自 84.1.0 修補；這不是一般文件上傳的處理路徑。

Accelerate 的 checkpoint index 路徑問題
[GHSA-4j2p-28q2-5m79](https://github.com/advisories/GHSA-4j2p-28q2-5m79)
仍須處理。專案沒有直接呼叫公告中的 `load_checkpoint_in_model` 或
`load_checkpoint_and_dispatch`；現有單 GPU `device_map` 仍依賴 Accelerate。
不可把單純升版視為已修補，也不可載入使用者提供的不可信 checkpoint。

GPU extra 不在 base 安裝、預設 CI 或公開 CPU 容器中。模型驗證應固定可信來源的完整
revision、使用 safetensors 並禁止 remote code；這些措施不代表任意 checkpoint 都安全。
安全升級的相容性 smoke 與固定 XFUND benchmark 分開保存；歷史 Torch 2.11.0+cu128
的 Recall@1／Recall@3 不得冒充新環境的重新量測結果。

Feature Freeze 期間，`.github/dependabot.yml` 以 `open-pull-requests-limit: 0` 停止例行 version-update PR，
不再用 `ignore` 隱藏特定套件。Dependabot security updates 維持啟用；若上述套件出現新的安全警示，
仍須依風險與重新評估條件個別處理。

## 維護者檢查

```powershell
uv lock --check
uv run pytest
uv run python scripts/verify_release.py
```

公開 repository 建議另外啟用 GitHub Secret scanning、Push protection、Dependabot security updates 與 CodeQL default setup。
