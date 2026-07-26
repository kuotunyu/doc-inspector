# GitHub 與 Hugging Face 同名發布

這份文件集中處理發布前 gate、遠端建立與推送、Private 驗收及失敗復原。
正式名稱在兩邊都固定為 `doc-inspector`：

- GitHub：`https://github.com/kuotunyu/doc-inspector`
- Hugging Face Space：`https://huggingface.co/spaces/steven0226/doc-inspector`
- Public live demo：`https://steven0226-doc-inspector.hf.space`

截至 2026-07-25，GitHub 主倉與 Hugging Face Docker Space 均已發布；Space
已完成 Private 合成範例／Gemini／JSON／Excel 全流程驗收並切換 Public。

發布順序固定為 **GitHub 主倉 → Hugging Face 部署鏡像**。GitHub 保存主要
程式碼與開發歷史；Hugging Face Space 使用從 GitHub 對應 commit 匯出的同一份
已驗收 source snapshot 建置公開服務，兩邊不要求共享 Git commit history。
這是本專案唯一的遠端發布、私人驗收與復原清單；容器原理與本機啟動方式另見
[DEPLOYMENT.md](../DEPLOYMENT.md)。協作代理不會代為執行 Git、登入帳號、
建立遠端或設定 Secrets。

## 0. 先跑本機 gate

在 PowerShell 進入專案根目錄：

```powershell
Set-Location '<專案資料夾>'
uv lock --check
uv run python scripts/verify_deployment.py
uv run --all-extras pytest --cov=doc_inspector --cov-report=term --cov-fail-under=85
uv run python -m compileall -q src scripts tests
uv run python scripts/run_product_evaluation.py --check
uv run python scripts/verify_public_docs.py
uv build --clear --no-build-isolation
uv run python scripts/verify_distribution.py
uv run python scripts/verify_release.py
```

全部成功才繼續。`verify_release.py` 不讀取 `.env` 真值，也不連線到外部服務。

預期結果：

- dependency lock 無漂移；全 extras 為 149 項測試通過、coverage 89%，
  GitHub Actions 的 base dependency 路徑為 146 passed、1 skipped、coverage 87%。
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

截至 2026-07-23，`kuotunyu/doc-inspector` Public repository 已由維護者建立，
且 `main` 已完成首次推送；後續維護不要重複建立 repository。

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
Commits。首版已由維護者建立為公開 commit `77b2e80`；後續精簡應另作小型
commit，不改寫首版歷史。

### 保持唯一 Contributor 身分

建立任何 commit 前先確認：

```powershell
git config user.name
git config user.email
```

電子郵件必須已綁定 GitHub 帳號 `kuotunyu`，或使用該帳號在 GitHub 設定頁提供
的 noreply 地址；不要使用 bot、協作工具或第二個未綁定身分建立 commit，也
不要在 commit message 保留其他身分的 `Co-authored-by` trailer。

推送前檢查本次所有 commit 的作者與共同作者：

```powershell
git log origin/main..HEAD --format='%h  %an <%ae>'
git log origin/main..HEAD --format='%B' |
  Select-String -Pattern '^\s*Co-authored-by:' -CaseSensitive:$false
```

第一個命令的每一筆都必須是 `kuotunyu` 且 email 已綁定該帳號；第二個命令
預期沒有輸出。若 GitHub 上出現 Dependabot 或其他 bot 建立的 PR，為維持唯一
Contributor，**不要直接 merge、squash 或 rebase 該 PR**；先在本機重現必要
更新、完整驗證，再由 `kuotunyu` 自己建立 commit。

確認所有待發布變更都已提交後，先確認既有遠端再推送：

```powershell
git branch -M main
git remote -v
git push origin main
```

本專案的 `origin` 已建立，不要重複新增。只有 `git remote -v` 確認完全沒有
`origin` 時，才執行
`git remote add origin https://github.com/kuotunyu/doc-inspector.git`，並以
`git push -u origin main` 建立 upstream。GitHub 官方步驟見
[Adding locally hosted code to GitHub](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)。

Push 完成後，以本機完整 HEAD 驗證「同一個 commit」的 GitHub push CI；不要
只看先前某一次綠燈：

```powershell
$publishedHead = git rev-parse HEAD
uv run python scripts/check_github_ci.py --expected-sha $publishedHead
uv run python scripts/check_github_contributors.py
```

第一個報告必須同時為 `sha_matches=true`、`status=completed`、
`conclusion=success`、`ci_passed=true`；若仍在 `queued`／`in_progress`，等待
後重跑。第二個報告必須為 `sole_contributor=true`、`logins` 只有 `kuotunyu`
且 `anonymous_contributor_count=0`。GitHub 官方說明 Contributors endpoint
可能快取數小時
（[List repository contributors](https://docs.github.com/en/rest/repos/repos#list-repository-contributors)）；
若剛 push 後結果未更新，先等候再重跑，不要用刪除或改寫歷史來試誤。也可開啟
[`kuotunyu/doc-inspector` Contributors](https://github.com/kuotunyu/doc-inspector/graphs/contributors)
人工確認。任一 checker 失敗都先停止，不要建立或同步 Space archive。

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

## 4. 將 GitHub 已驗收版本同步到 Space

先在 Hugging Face 的 Access Tokens 頁建立具備該 Space 寫入權限的 token，並用
官方 `hf` CLI 安全登入；token 不要貼到聊天、命令歷史或 repository：

```powershell
uvx --from huggingface_hub hf auth whoami
```

本專案的公開文件含 PNG。未設定 Xet 的一般 `git push` 會被 Hugging Face 的
binary policy 拒絕；直接對專案根目錄執行 `hf upload` 又可能把 `.git`、
`.venv` 或本機 cache 一起掃進去。因此固定從 **GitHub 已推送且工作目錄乾淨的
HEAD** 建立 source-only staging directory，再交給支援 Xet 的官方 CLI：

```powershell
git status --short

$hfStage = Join-Path $env:TEMP ("doc-inspector-hf-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $hfStage | Out-Null

git -c core.autocrlf=false archive `
  --format=zip `
  --output (Join-Path $hfStage "repo.zip") `
  HEAD
Expand-Archive `
  -LiteralPath (Join-Path $hfStage "repo.zip") `
  -DestinationPath (Join-Path $hfStage "repo")

$repoRoot = Join-Path $hfStage "repo"
$repoPrefix = $repoRoot.TrimEnd('\') + '\'
$trackedFiles = @(git ls-tree -r --name-only HEAD)
$archiveFiles = @(
  Get-ChildItem -LiteralPath $repoRoot -Recurse -File |
    ForEach-Object {
      $_.FullName.Substring($repoPrefix.Length).Replace('\', '/')
    }
)

$pathDiff = @(
  Compare-Object `
    ($trackedFiles | Sort-Object) `
    ($archiveFiles | Sort-Object)
)
if ($pathDiff) {
  $pathDiff
  throw 'Archive 與 Git HEAD 的檔案清單不一致。'
}

$byteMismatches = @(
  foreach ($path in $trackedFiles) {
    $expectedBlob = (git rev-parse "HEAD:$path").Trim()
    $archivePath = Join-Path $repoRoot ($path.Replace('/', '\'))
    $actualBlob = (git hash-object --no-filters -- $archivePath).Trim()
    if ($expectedBlob -ne $actualBlob) {
      $path
    }
  }
)
if ($byteMismatches) {
  $byteMismatches
  throw 'Archive 內容不是 Git HEAD 的 byte-exact blob。'
}

"Archive verified: $($archiveFiles.Count) byte-exact files"

uvx --from huggingface_hub hf upload `
  steven0226/doc-inspector `
  $repoRoot `
  . `
  --repo-type=space `
  --commit-message="deploy: 同步已驗收 GitHub 版本"
```

第一行 `git status --short` 必須沒有輸出；若有未提交變更，先停止並處理 GitHub
主倉。`git -c core.autocrlf=false ...` 只對這一次 archive 覆寫 Git 設定，避免
Windows 的 CRLF 工作目錄設定改寫 archive 內的文字檔；否則部署雖可執行，
仍無法通過與 GitHub blob 的 byte-exact source gate。上傳前的兩段 preflight
會先確認檔案清單相同，再以 `git hash-object --no-filters` 驗證每個 archive
檔案的原始 bytes 對應 HEAD blob；任一差異都會停止。`git archive HEAD` 天然
排除 `.git`、未追蹤檔與被忽略的本機資料。成功時 CLI 會顯示 `Uploaded` 與
Hugging Face commit URL。

這個 Space 已經完成初始建立，後續每次更新都重複上述 archive/upload 流程；
不要再對 Space 使用 force push，也不要直接上傳專案根目錄。發布後到 Space
的 **Files** 檢查 source snapshot，再等待 Docker build 顯示 **Running**。

Space 顯示 Running 後，先比對該部署與已通過 CI 的 GitHub commit 之
runtime 關鍵檔，再做首頁健康檢查：

```powershell
uv run python scripts/check_space_snapshot.py --github-sha $publishedHead
uv run python scripts/check_live_space.py `
  --url 'https://steven0226-doc-inspector.hf.space'
```

第一個報告只比對固定的 runtime／build／dependency 關鍵檔，不宣稱全
repository snapshot 等同；必須為 `critical_source_match=true` 且
`mismatched_files=[]`。若失敗時 `line_ending_only_mismatches` 有值但
`content_mismatches=[]`，代表檔案內容只差 CRLF／LF，應回到上方確認 archive
使用 `-c core.autocrlf=false`，不可降低 byte-exact gate。第二個報告必須為
`healthy=true`。兩者都只讀取公開 HTTPS 檔案，不使用 token、不上傳文件，也
不呼叫模型。

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

2026-07-24 實跑結果：匿名 HTTPS 一次回傳 HTTP 200、HTML 內含「文件預檢所」，
`healthy=true`；檢查未上傳文件、未呼叫模型，也未讀取 `.env`。

## 7. 回復方式

若遠端驗證失敗，先讓 Space 保持 Private 或撤回公開流量，不要刪除本機已驗收
版本。若金鑰疑似出現在 log 或設定中：

1. 立即在供應商後台撤銷並輪替金鑰。
2. 從 Space Settings 移除舊 Secrets。
3. 清理可能含秘密的遠端紀錄，再設定新金鑰。
4. 重新跑私人驗收；通過前不要切回 Public。

## 8. Phase 7 GitHub 工程可信度設定

以下操作需要 repository owner 登入 GitHub；本機檔案無法代替遠端設定。

### 確認 CI

1. 開啟 repository 的 **Actions**。
2. 確認 `CI` 在 `ubuntu-latest`、`windows-latest` 都通過。
3. 若 Actions 尚未啟用，按下啟用按鈕後重新執行 workflow。

CI 不需要 secrets，也不會呼叫模型 API。

### 啟用 CodeQL default setup

1. 進入 **Settings → Security → Advanced Security**。
2. 在 **CodeQL analysis** 選擇 **Set up → Default**。
3. 選擇 Python 並啟用。

本專案採 GitHub 建議的 default setup，不另提交 advanced CodeQL workflow，避免同時存在兩份 CodeQL workflow。

### 啟用供應鏈與秘密保護

在 **Settings → Security → Advanced Security** 確認：

- Dependabot alerts。
- Dependabot security updates。
- Secret scanning。
- Push protection。
- Private vulnerability reporting。

`.github/dependabot.yml` 會每週檢查 uv、GitHub Actions 與 Docker 更新；安全更新仍以 GitHub 遠端設定為準。

### 設定 main branch 保護

在 **Settings → Branches** 或 **Rules → Rulesets** 為 `main` 建立規則：

- Require a pull request before merging。
- Require status checks to pass。
- 指定兩個 `CI / Python 3.11` matrix checks。
- Require branches to be up to date before merging。
- Block force pushes。
- Block deletions。

如果是單人作品集，可先不要求 approval 人數，但仍保留 Pull Request 與 CI gate。

### v1.0.0 Release 與後續版本

`v1.0.0` 已於 2026-07-25 發布。若要重建 Release 或發布後續版本，先確認
作者驗收、CI 與安全掃描都通過，再依序執行：

1. 確認 `main` 是要發布的 commit。
2. 建立 annotated tag `v1.0.0`。
3. 推送 tag。
4. 在 GitHub **Releases → Draft a new release** 選擇 `v1.0.0`。
5. Release title 使用 `v1.0.0｜文件預檢所`。
6. 內容以 [`docs/RELEASE_NOTES_v1.0.0.md`](RELEASE_NOTES_v1.0.0.md) 為基礎，依實際版本更新。
7. 發布後重新確認 Live Demo 與 README 連結。

Tag 與 Release 都是公開且有外部影響的操作，必須由作者人工執行。
