# v1.0.0 Release Notes

> 發布於 2026-07-25。Windows／Ubuntu CI 於 `main` 全綠，發布包驗證與隔離 wheel 安裝 smoke 通過。

## 文件預檢所

`doc-inspector` 把圖片或 PDF 轉成固定 schema，保留欄位頁碼與短證據，再以確定性規則檢查必填、日期、身分證件與金額一致性。結果會直接告訴使用者哪些項目需要修正、哪些需要人工確認。

## Highlights

- 正體中文、可操作的四步驟文件預檢 UI。
- `subsidy_application`、`receipt` 兩個 versioned schema。
- 兩個可切換雲端 provider；模型設定與 secrets 不寫死。
- 紅／黃／綠規則結果與 JSON／Excel 匯出。
- 不含真實個資的 synthetic 綠／黃／紅 demo。
- Windows／Ubuntu CI、coverage gate、reproducible build、archive hygiene、隔離 wheel 安裝 smoke 與 release verifier。
- `1.0.0` wheel／sdist 具備作者 `kuotunyu`、MIT、Python 版本、關鍵字與 GitHub／Live Demo 等公開 package metadata。
- 24 個離線決策層 regression cases，完整通過燈號與 issue contract。
- 公開 Case Study、評估方法、安全政策與貢獻指南。

## Evaluation

| 評估 | 結果 |
|---|---:|
| 決策層 exact case match | 24 / 24 |
| 決策層紅燈／黃燈 issue recall | 100%／100% |
| XFUND Gemini Micro F1 | 0.4471 |
| XFUND OpenAI Micro F1 | 0.4819 |
| ColQwen2 Recall@1／Recall@3 | 0.95／1.00 |

決策層 100% 是固定 synthetic extraction 的 regression 結果，不代表 OCR/VLM 端到端準確率。

## Try it

- [Live demo](https://steven0226-doc-inspector.hf.space)
- [Case Study](CASE_STUDY.md)
- [Decision evaluation](DECISION_EVALUATION.md)

## Safety

這是送件前技術預檢，不取代正式資格、法律或行政判斷。公開 demo 會把文件傳給使用者選定的雲端 provider，請勿上傳無權處理的資料。
