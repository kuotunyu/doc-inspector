"""Run the offline decision-layer product regression suite."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from doc_inspector.product_eval import (
    evaluate_decision_suite,
    load_decision_suite,
    write_decision_report,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("data/evaluation/decision_cases.json"),
        help="Versioned decision-case definition.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/assets/decision-evaluation.json"),
        help="Destination for the machine-readable report.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify that the committed report matches a fresh offline evaluation.",
    )
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    suite = load_decision_suite(args.cases)
    report = evaluate_decision_suite(suite)
    if args.check:
        if not args.output.is_file():
            print(f"找不到待檢查的 report：{args.output}")
            return 1
        committed = json.loads(args.output.read_text(encoding="utf-8"))
        current = report.model_dump(mode="json")
        if committed != current:
            print("決策層評估報告已過期，請重新執行不含 --check 的命令。")
            return 1
    else:
        write_decision_report(report, args.output)
    metrics = report.metrics
    print(f"決策層回歸評估：{metrics.exact_case_matches}/{metrics.case_count} cases")
    print(f"整體燈號 accuracy：{metrics.overall_status_accuracy:.1%}")
    print(f"紅燈 issue recall：{metrics.red_issue_recall:.1%}")
    print(f"黃燈 issue recall：{metrics.yellow_issue_recall:.1%}")
    print(f"Issue precision：{metrics.issue_precision:.1%}")
    print(f"Report：{args.output}")
    print("範圍：固定 synthetic extraction 的規則與使用者決策，不代表端到端 OCR/VLM 準確率。")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
