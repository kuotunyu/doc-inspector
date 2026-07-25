# CPU 容器部署準備

這個映像只執行雲端供應商模式，不安裝 `local-retrieval` extra，因此不會把 CUDA、Torch 或 ColQwen2 權重放進免費 CPU 容器。原始文件只存在工作程序的暫存空間；上傳與匯出檔都放在 Gradio 管理的 cache，每 10 分鐘清理且關閉時再清空。介面要求使用者勾選雲端傳輸同意；analytics、monitoring 與事件 API 不公開，等待佇列最多 8 件。

完整交付、私人驗收與復原順序見
[docs/REMOTE_SETUP.md](docs/REMOTE_SETUP.md)。下列命令只驗證本機容器，不會建立遠端服務。

## 發布前本機 gate

```powershell
uv lock --check
uv run python scripts/verify_deployment.py
uv run python scripts/run_product_evaluation.py --check
uv run python scripts/verify_public_docs.py
uv run --all-extras pytest --cov=doc_inspector
uv build --clear --no-build-isolation
uv run python scripts/verify_distribution.py
uv run python scripts/verify_release.py
```

八個命令都成功後，才進入人工 Git 與遠端平台步驟。`verify_distribution.py` 只檢查乾淨 build 產物，並用 uv cache 在全新 virtual environment 離線安裝 wheel 與完整相依；`verify_release.py` 只讀取公開交付檔與空白設定範例。兩者都不讀取 `.env` 真值。

## 本機驗證

```powershell
docker build -t doc-inspector:local .
docker run --rm -p 7861:7861 `
  -e GOOGLE_API_KEY `
  -e GEMINI_MODEL `
  -e OPENAI_API_KEY `
  -e OPENAI_MODEL `
  doc-inspector:local
```

開啟 `http://127.0.0.1:7861`。7860 保留給其他專案；不要把 `.env` 複製進映像。正式平台應以 Secrets 管理介面注入金鑰。若平台提供 `PORT`，設定會自動採用；否則預設為 7861。

## 上線前人工步驟

1. 由維護者選定免費 CPU 容器平台並建立私人測試服務。
2. 以平台 Secrets 注入 `GOOGLE_API_KEY`、`OPENAI_API_KEY` 與模型 ID；不要寫進映像、設定檔或建置參數。
3. 先用合成文件驗證上傳、抽取、規則檢查與 JSON／Excel 下載。
4. 確認日誌沒有文件內容、API 回應或金鑰，再決定是否公開 URL。
5. 公開後才由維護者把 live demo URL 加入 README。

此專案不自動建立服務、不登入平台、不推送映像，也不修改遠端 Secrets。

## Hugging Face Docker Space

本專案的公開目標是 Hugging Face Docker Space。README front matter 已設定：

目前公開服務已於 2026-07-24 完成 Private 全流程驗收與匿名 HTTPS 健康檢查：
[開啟文件預檢所](https://steven0226-doc-inspector.hf.space)。

```yaml
sdk: docker
app_port: 7861
```

Dockerfile 會讓 Gradio 綁定 `0.0.0.0:7861`，與 Space 的 `app_port` 一致。

### 建立方式

1. 登入 Hugging Face，建立新的 Space。
2. SDK 選擇 **Docker**；初次測試建議先設為 **Private**。
3. Hardware 選擇 **CPU Basic**。
4. 由維護者把已驗收的專案檔案推送到 Space repository。
5. 在 Space Settings 設定下列 Secrets：
   - `GOOGLE_API_KEY`
   - `OPENAI_API_KEY`
6. 在 Space Settings 設定下列 Variables：
   - `GEMINI_MODEL`
   - `OPENAI_MODEL`
   - `MODEL_MAX_TOKENS=4096`
   - `PUBLIC_MAX_REQUESTS_PER_HOUR=60`
7. 等待 Docker build 完成，先依
   [遠端發布指南](docs/REMOTE_SETUP.md#6-private-驗收後才公開)
   使用四種合成案例驗收。
8. 確認 API 費用上限、日誌與隱私後，再把 visibility 改成 **Public**，讓其他人可以使用。

Public Space 的程式碼與執行中的 app 都會公開。若要讓 app 公開但程式碼保持私有，需要 Hugging Face 的 Protected visibility；此功能屬付費方案。

### 成本與生命週期

- CPU Basic 本身沒有每小時計算費，但 Hugging Face 現行政策可能要求付費帳戶才能建立新的 Gradio／Docker compute Space；建立頁面會顯示你的帳戶是否符合。
- CPU Basic 為 2 vCPU、16 GB RAM、50 GB 暫存磁碟，足以執行本專案的雲端 provider 模式。
- 免費硬體閒置約 48 小時後會休眠；下一位訪客會觸發喚醒。
- Space 磁碟不是永久儲存；本專案不需要持久資料，且上傳文件只應存在暫存與 cache 生命週期內。
- 公開使用者的模型請求會消耗 Space 擁有者設定的 API key 配額；公開前必須確認供應商端支出上限。
- 映像預設以單一執行程序共用的滾動時窗限制每小時 60 次預檢；重啟後會重置，
  不是 per-user 身分辨識或防禦邊界，不能取代供應商端的硬性支出上限。

GitHub 與 Hugging Face 使用同一個 `doc-inspector` 名稱的完整人工步驟見
[docs/REMOTE_SETUP.md](docs/REMOTE_SETUP.md)。

Space 公開後可用下列命令做不產生模型費用的唯讀健康檢查：

```powershell
uv run python scripts/check_live_space.py `
  --url 'https://steven0226-doc-inspector.hf.space'
```

工具只確認 HTTPS、HTTP 200、HTML Content-Type 與「文件預檢所」標題，不會
上傳文件、呼叫模型或讀取 `.env`。
