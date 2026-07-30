"""Run the offline evidence-provenance localization benchmark.

Runs entirely on the committed synthetic corpus: no network, no API key, no
model download, and no GPU. The corpus manifest is read-only here, so a run can
never relabel the ground truth it is scored against.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from doc_inspector.provenance_eval import (
    GATE_MIN_PAGE_ACCURACY,
    GATE_MIN_VERIFIED_BBOX_HIT_RATE,
    comparable_report,
    evaluate_corpus,
    load_corpus,
    write_provenance_report,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/evaluation/provenance/manifest.json"),
        help="Committed corpus manifest containing the recorded ground truth.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/assets/provenance-evaluation.json"),
        help="Destination for the machine-readable report.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the committed report still matches a fresh offline run.",
    )
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = _arguments()
    corpus = load_corpus(args.manifest)
    report = evaluate_corpus(corpus, args.manifest.parent)

    if args.check:
        if not args.output.is_file():
            print(f"找不到待檢查的 report：{args.output}")
            return 1
        committed = json.loads(args.output.read_text(encoding="utf-8"))
        if comparable_report(committed) != comparable_report(report):
            print("來源核驗評估報告已過期，請重新執行不含 --check 的命令。")
            return 1
    else:
        write_provenance_report(report, args.output)

    metrics = report.metrics
    print(f"語料：{metrics.field_count} 欄位，{metrics.localizable_field_count} 個可解析")
    print(f"Corpus SHA-256 驗證：{'通過' if report.corpus_checksums_verified else '失敗'}")
    print(f"狀態完全相符：{metrics.status_exact_matches}/{metrics.field_count}")
    print(
        f"可解析欄位 page accuracy：{metrics.page_localization_accuracy:.2%}"
        f"（門檻 {GATE_MIN_PAGE_ACCURACY:.0%}）"
    )
    print(f"可解析欄位 bbox 覆蓋率：{metrics.bbox_localization_coverage:.2%}")
    print(
        f"所有有宣稱欄位的 bbox 覆蓋率："
        f"{metrics.overall_bbox_coverage:.2%}"
        f"（{metrics.predicted_bbox_count}/{metrics.claimed_field_count}）"
    )
    print(f"bbox hit rate（IoU ≥ {report.region_hit_iou}）：{metrics.bbox_hit_rate:.2%}")
    print(
        f"verified bbox hit rate：{metrics.verified_bbox_hit_rate:.2%}"
        f"（門檻 {GATE_MIN_VERIFIED_BBOX_HIT_RATE:.0%}）"
    )
    print(f"false verified rate：{metrics.false_verified_rate:.2%}（門檻 0%）")
    print(f"ambiguous 偵測率：{metrics.ambiguous_detection_rate:.2%}")
    print(f"unresolved 比例：{metrics.unresolved_rate:.2%}")
    print(f"平均／中位 IoU：{metrics.mean_iou:.4f}／{metrics.median_iou:.4f}")
    print(
        f"定位延遲 p50／p95／max：{report.latency_ms.p50_ms:.3f}／"
        f"{report.latency_ms.p95_ms:.3f}／{report.latency_ms.max_ms:.3f} ms"
    )
    if report.gate_failures:
        print(f"未通過的 gate：{'、'.join(report.gate_failures)}")
    print(f"Report：{args.output}")
    print("範圍：合成 PDF 語料的定位能力與誠實度，不代表真實文件端到端準確率。")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
