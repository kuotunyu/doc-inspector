# GitHub 與 Hugging Face 同名發布

這份文件集中處理發布前 gate、遠端建立與推送、Private 驗收及失敗復原。
正式名稱在兩邊都固定為 `doc-inspector`：

- GitHub：`https://github.com/kuotunyu/doc-inspector`
- Hugging Face Space：`https://huggingface.co/spaces/steven0226/doc-inspector`

發布順序固定為 **GitHub 主倉 → Hugging Face 部署鏡像**。GitHub 保存主要
程式碼與開發歷史；Hugging Face Space 使用同一份已驗收內容建置公開服務。
這是本專案唯一的遠端發布、私人驗收與復原清單；容器原理與本機啟動方式另見
[DEPLOYMENT.md](../DEPLOYMENT.md)。協作代理不會代為執行 Git、登入帳號、
建立遠端或設定 Secrets。

## 0. 先跑本機 gate

在 PowerShell 進入專案根目錄：

```powershell
Set-Location '<專案資料夾>'
uv lock --check
uv run python scripts/verify_deployment.py
uv run python scripts/verify_release.py
uv run --all-extras pytest --cov=doc_inspector
uv build
```

全部成功才繼續。`verify_release.py` 不讀取 `.env` 真值，也不連線到外部服務。

預期結果：

- dependency lock 無漂移，116 項測試通過且總 coverage 為 89%。
- CPU 容器排除 GPU extra、`.env`、原始資料與模型權重，並以非 root 使用者執行。
- 上傳／匯出共用受管理 cache；analytics、monitoring、事件 API 與無界佇列未開放。
- 公開容器的共用請求上限測試通過；本機預設不限，容器預設每小時 60 次。
- `dist/` 產生 wheel 與 source distribution；`dist/` 不納入 Git。

若 UI 或公開執行設定有變更，再用兩個 PowerShell 終端執行離線瀏覽器 gate：

```powershell
# 終端 A
uv run python scripts/serve_ui_fixture.py --port 7862

# 終端 B
$env:UI_TEST_URL = 'http://127.0.0.1:7862'
$env:UI_TEST_EXPECT_ACTION_PLAN = '1'
uv run python scripts/verify_ui_layout.py
uv run python scripts/audit_ui_quality.py
```

完成後在終端 A 按 `Ctrl+C`。兩個稽核腳本預設拒絕 7861 或遠端網址，避免測試
誤觸真實模型；離線 fixture 不讀 `.env`、不呼叫模型。

## 1. 建立同名 GitHub repository

1. 開啟 [GitHub New repository](https://github.com/new?name=doc-inspector&visibility=public)。
2. Owner 選自己的 GitHub 帳號。
3. Repository name 確認為 `doc-inspector`。
4. Visibility 選 **Public**。
5. **不要**勾選 Add README、Add .gitignore 或 Choose a license；本機已經有這些檔案，預先建立會造成歷史衝突。
6. 按 **Create repository**。

截至 2026-07-23，`kuotunyu/doc-inspector` 空白 Public repository 已由維護者
建立；若它仍存在，不要重複建立。

GitHub 官方也建議匯入既有本機專案時不要預先產生上述檔案：
[Creating a new repository](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository)。

## 2. 由維護者檢查並推送 GitHub

先確認本機狀態；不要直接複製未知帳號的 URL：

```powershell
git status
git remote -v
```

若 `git status` 顯示「not a git repository」，才執行：

```powershell
git init -b main
```

逐項確認 `git status --short` 沒有 `.env`、真實文件、模型權重、benchmark、
outputs 或 logs。若目前變更尚未提交，依功能拆分正體中文 Conventional
Commits。首版已由維護者建立為本機 commit `1dee3b4`；後續精簡應另作小型
commit，不改寫首版歷史。

確認所有待發布變更都已提交後，設定實際遠端：

```powershell
git branch -M main
git remote add origin https://github.com/kuotunyu/doc-inspector.git
git push -u origin main
```

若 `origin already exists`，不要再新增；先看 `git remote -v`，確認它是否就是
剛建立的 `doc-inspector`。GitHub 官方步驟見
[Adding locally hosted code to GitHub](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)。

## 3. 建立同名 Hugging Face Docker Space

1. 開啟 [Create a new Space](https://huggingface.co/new-space)。
2. Owner 選 `steven0226`。
3. Space name 填 `doc-inspector`。
4. License 選 **MIT**。
5. SDK 選 **Docker**。
6. Hardware 選 **CPU Basic**。
7. 初次驗證先選 **Private**。
8. 建立完成後，先不要貼任何 API key 到檔案或討論區。

Space 也是 Git repository，每次 push 後會自動重新建置與啟動：
[Spaces Overview](https://huggingface.co/docs/hub/main/spaces-overview)。

## 4. 將 GitHub 已驗收版本推到 Space

先在 Hugging Face 的 Access Tokens 頁建立具備該 Space 寫入權限的 token，並在
本機安全登入；token 不要貼到聊天、命令歷史或 repository。接著在專案根目錄
加入第二個 remote：

```powershell
git remote add hf https://huggingface.co/spaces/steven0226/doc-inspector
git fetch hf main
```

全新 Space 會有平台產生的初始 commit。**只有在確認 remote URL 正確、Space
是剛建立且沒有要保留的內容時**，才用下列一次性命令，以本機已驗收內容取代
初始骨架：

```powershell
git push --force-with-lease hf main:main
```

第一次對齊後，日後更新使用一般推送，不再強制：

```powershell
git push origin main
git push hf main:main
```

## 5. 設定 Space，不把金鑰提交到 Git

到 Space 的 **Settings → Repository secrets** 加入：

- `GOOGLE_API_KEY`
- `OPENAI_API_KEY`

到 **Settings → Variables** 加入：

- `GEMINI_MODEL`
- `OPENAI_MODEL`
- `MODEL_MAX_TOKENS=4096`
- `PUBLIC_MAX_REQUESTS_PER_HOUR=60`

`PUBLIC_MAX_REQUESTS_PER_HOUR` 是單一執行程序共用的滾動時窗上限；設為 `0`
代表關閉。它能減少意外連點和一般濫用，但重啟後會重置，也不是依使用者辨識
的安全機制。供應商後台的硬性支出上限仍然必須保留。

## 6. Private 驗收後才公開

### 私人驗收清單

只使用固定種子的合成文件，逐項確認：

1. 補助綠、黃、紅與收據綠四種案例都能完成。
2. 雲端同意預設未勾選；未勾選時不得送出請求。
3. 處理中按鈕停用，完成或錯誤後恢復。
4. 修正清單、辨識內容、全部檢核與 JSON 分頁都可閱讀。
5. JSON／Excel 可下載，且沒有絕對路徑、raw API 回應或試算表公式注入。
6. Space log 沒有文件內容、完整 API 回應、金鑰或個資。
7. 暫時把 `PUBLIC_MAX_REQUESTS_PER_HOUR` 設為小值，確認超限時顯示稍後再試
   且不呼叫模型；完成後恢復為 60。
8. 供應商帳戶仍有硬性支出上限。

### 公開前最後確認

- 確認平台費用、休眠、流量與檔案大小限制。
- 確認隱私告知與「非正式資格／法律判斷」文案仍可見。
- 確認只公開合成範例，不公開授權不明的政府 PDF、XFUND 原始資料或私有文件。
- 確認接受公開 URL 可被任何人呼叫，並可能產生模型 API 費用。
- Public Space 會公開 app 與原始碼；若要隱藏原始碼但公開 app，需使用付費的
  Protected visibility。

通過後，把 Space visibility 從 Private 改為 Public。正式網址預期為：

`https://steven0226-doc-inspector.hf.space`

實際網址以 Space 頁面顯示為準。公開後可執行唯讀健康檢查；它只讀取首頁
HTML，不上傳文件、不呼叫模型，也不讀取 `.env`：

```powershell
uv run python scripts/check_live_space.py `
  --url 'https://steven0226-doc-inspector.hf.space'
```

回報 `healthy: true` 後，再更新 README 狀態與正式網址。

## 7. 回復方式

若遠端驗證失敗，先讓 Space 保持 Private 或撤回公開流量，不要刪除本機已驗收
版本。若金鑰疑似出現在 log 或設定中：

1. 立即在供應商後台撤銷並輪替金鑰。
2. 從 Space Settings 移除舊 Secrets。
3. 清理可能含秘密的遠端紀錄，再設定新金鑰。
4. 重新跑私人驗收；通過前不要切回 Public。
