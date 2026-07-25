# 決策層產品評估

## 目的

這份評估驗證 `doc-inspector` 在取得固定、已結構化的 extraction 後，能否穩定產生正確燈號與問題清單。它回答的是：

- 必填欄位遺漏是否被攔下？
- 無效日期與日期先後是否被正確區分？
- 台灣身分證與其他證件是否採用合適的判斷？
- 補助與收據的金額關係是否被正確檢查？
- 無法安全自動判斷時，是否保留黃燈而不是猜測？

它**不評估** OCR、VLM、版面辨識或雲端模型抽取準確率。

## 評估資料

- 定義檔：[`data/evaluation/decision_cases.json`](../data/evaluation/decision_cases.json)
- 固定 synthetic base：`subsidy_green`、`subsidy_yellow`、`receipt_green`
- 案例數：24
- 分布：綠燈 2、黃燈 3、紅燈 19
- 預期非綠燈 issues：37（紅燈 21、黃燈 16）
- 涵蓋：2 個 schema、13 個非綠燈 rule ID

每個案例明確寫出：

1. Synthetic base。
2. 欄位 mutation。
3. 預期整體燈號。
4. 預期 issue signature：`rule_id + level + field_paths`。

預期值不是由現行規則輸出自動回填，因此可以偵測規則行為漂移。

## 指標

| 指標 | 定義 | 結果 |
|---|---|---:|
| Exact case match | 燈號、遺漏 issue、額外 issue 全部一致 | 24 / 24 |
| Overall status accuracy | 預期與實際整體燈號一致 | 100% |
| Issue precision | 預測 issue 中符合預期的比例 | 100% |
| Issue recall | 預期 issue 中成功出現的比例 | 100% |
| Red issue recall | 預期紅燈 issue 的召回率 | 100% |
| Yellow issue recall | 預期黃燈 issue 的召回率 | 100% |

完整 machine-readable 報告：[`docs/assets/decision-evaluation.json`](assets/decision-evaluation.json)。

## 執行方式

重新產生報告：

```powershell
uv run python scripts/run_product_evaluation.py
```

CI 使用只讀檢查，確認固定案例、程式與 committed report 一致：

```powershell
uv run python scripts/run_product_evaluation.py --check
```

兩個命令都不讀 `.env` 真值、不呼叫網路或付費 API。

## Error analysis 輸出

每個案例都保留：

- `expected_overall_level`
- `predicted_overall_level`
- `expected_issues`
- `predicted_issues`
- `missing_issues`
- `unexpected_issues`
- `passed`

只要規則漏報、誤報或整體燈號錯誤，CLI 會以非零 exit code 結束，CI 隨即失敗。這比只有 aggregate accuracy 更容易定位回歸。

## 如何解讀 100%

100% 代表目前 24 個人工定義 contract 全部通過，適合作為規則層 regression gate。它不表示：

- 文件抽取在真實世界達到 100%。
- 所有政府表單與收據格式都已涵蓋。
- 綠燈代表正式資格通過。
- 規則不存在未知盲點。

端到端抽取能力應另外看 XFUND benchmark、真實版面 error taxonomy 與人工核對結果；不可把本報告的數字用作模型準確率宣稱。

