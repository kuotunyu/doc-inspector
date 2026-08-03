# Changelog

本檔記錄使用者可感知的變更。版本採 [Semantic Versioning](https://semver.org/)。

## [Unreleased]

## [1.1.1] - 2026-08-03

### Fixed

- 發布封存明確排除本機私密與 agent 文件，並拒絕 sdist 內任何非追蹤來源檔案。
- 發布去識別的 XFUND 抽取與 ColQwen 檢索聚合證據，公開指標可直接連回機器可讀 artifact。
- 發布指南改用版本參數與已驗證 release commit，既有 tag 維持不可變。

## [1.1.0] - 2026-07-30

### Added

- 來源核驗（verified evidence provenance）：抽取完成後以確定性後處理，在文件自己的
  文字層比對模型引用的原文，區分 `verified`／`approximate`／`ambiguous`／`page_only`／
  `unresolved` 五種狀態。找不到唯一可靠位置時明確說不知道，不生成 bounding box。
- `InspectionBundle` 新增向後相容的 `provenance` 欄位（`provenance_version` 1.0.0），
  座標採與 DPI、crop box、頁面旋轉及縮放無關的 `normalized_1000_top_left` 空間。
- 介面新增「來源核驗」分頁：可選欄位、查看核驗結果，並在原始頁面畫出半透明的證據
  highlight；狀態文字、色塊與說明各自不同，`unresolved` 不會顯示成成功綠燈。
- Excel 匯出新增 `provenance` 工作表；`metadata` 工作表加上 provenance 版本與統計。
- 獨立的來源核驗評估：4 份合成 PDF、61 個欄位（51 個有 ground-truth 位置），涵蓋
  重複值、錯誤頁碼、幻覺證據、換行接合、旋轉頁、算繪後縮放與純影像頁；ground truth
  由文件生成器直接記錄並以 SHA-256 鎖定，另附 machine-readable 報告與 CI gate。
- 可選的本機證據 OCR extra（`local-ocr`）；未安裝時安全退化為 `page_only`，不中斷預檢。
- 三頁合成 PDF 範例，前兩頁有真實文字層、第三頁只有影像，可一次示範五種核驗狀態。

### Changed

- 公開倉庫移除可重建的 UI 稽核報告與非展示截圖，產物改寫入被 Git 忽略的 `outputs/ui-audit/`；產品、UI 與部署說明整合進 Case Study 與單一遠端指南。
- 貢獻指南與安全政策移至 GitHub 支援的 `.github/` 位置，降低根目錄噪音而不移除社群入口。
- Package author 與 repository CODEOWNERS 固定為 `kuotunyu`，並納入 release／distribution verifier。
- README 與遠端指南對齊已發布的 v1.0.0、最新本機測試與 UI 對比證據。
- Windows／Ubuntu CI 新增 CPU 部署安全 verifier；公開維護文件統一乾淨 build、compileall、distribution 與 release gates。
- 遠端指南加入 GitHub commit identity、共同作者／bot PR 防護、唯一 Contributor 人工確認與無認證唯讀 API 檢查。
- 依既有的單一 Contributor 政策，在本機重現 Dependabot 提出的更新而非合併 bot PR：
  `langchain-openai` 1.4.1（連帶 `langchain-core` 1.5.2）與容器基底 `uv` 映像 0.11.32。
- 新增以完整 commit SHA 驗證指定 GitHub push CI 的無認證唯讀檢查，避免把舊 workflow 綠燈誤當成新版本已通過。
- 新增 GitHub 指定 commit 與 Hugging Face Space 的 runtime 關鍵檔逐位元比對，讓部署來源漂移可被機器驗證。
- PDF 文字層改用逐字 bbox。`get_text("words")` 不在全形空白斷詞，會讓整行中文變成單一
  token，使證據 highlight 框到不相干的內容。
- 瀏覽器 gate 改以 `domcontentloaded` 加元素等待取代 `networkidle`：介面現在有 Gradio
  session state，其 heartbeat 串流會持續開著，`networkidle` 永遠不會觸發。

### Fixed

- 固定已驗收的淺色 civic theme，避免瀏覽器深色系統偏好讓 Gradio 文字 token 與淺色表面形成低對比。
- UI gate 同時驗證 light／dark 系統偏好，關鍵正文對比不得低於 4.5:1。
- Release verifier 與決策評估 CLI 主動使用 UTF-8 stdout，避免 Windows 非 UTF-8 shell 破壞 JSON 或正體中文輸出。

## [1.0.0] - 2026-07-25

### Added

- Windows／Ubuntu、Python 3.11 的離線 GitHub Actions CI。
- 24 個決策層產品回歸案例、machine-readable report 與 error analysis。
- Case Study、貢獻指南、安全政策、Pull Request template 與 Dependabot 設定。

### Changed

- Release verifier 同步檢查 CI、評估與開源治理產物。

### Fixed

- CI 在 Linux 補裝 `fonts-noto-cjk`，修正 demo 產圖找不到正體中文字型導致的測試失敗。
- 離線 wheel smoke 前預熱 runtime 依賴快取，修正冷快取環境下 transitive 依賴解析失敗。

## [0.1.0] - 2026-07-24

### Added

- 補助申請表與收據兩個固定 schema。
- 可切換 Gemini／OpenAI structured extraction provider。
- 必填、日期、台灣身分證與金額一致性規則。
- 正體中文 Gradio 操作介面、紅／黃／綠修正清單。
- JSON／Excel 匯出與不含真實個資的 synthetic demo。
- XFUND 抽取 benchmark 與 optional ColQwen2 頁面檢索。
- Docker CPU 部署、GitHub repository 與 Hugging Face live demo。
