# Changelog

本檔記錄使用者可感知的變更。版本採 [Semantic Versioning](https://semver.org/)。

## [Unreleased]

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

