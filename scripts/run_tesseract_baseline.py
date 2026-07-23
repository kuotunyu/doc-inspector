"""Run the resumable XFUND Tesseract + regex baseline and aggregate metrics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
from time import perf_counter

from doc_inspector.benchmark import (
    BenchmarkPair,
    build_evaluation_split,
    load_xfund_documents,
    run_tesseract,
    score_by_split,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="執行 XFUND Tesseract chi_sim+eng baseline。")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/xfund"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/benchmark"))
    parser.add_argument("--tesseract", default="tesseract")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    executable = shutil.which(args.tesseract)
    if executable is None:
        raise SystemExit("找不到 Tesseract；請安裝後確認 PATH 與 chi_sim、eng 語言包。")

    raw_dir = args.raw_dir.resolve()
    train = load_xfund_documents(raw_dir / "zh.train.json", "train_holdout")
    val = load_xfund_documents(raw_dir / "zh.val.json", "val")
    evaluation, _ = build_evaluation_split(train, val)
    prediction_dir = args.output_dir / "predictions" / "tesseract"
    prediction_dir.mkdir(parents=True, exist_ok=True)
    predictions: dict[str, list[BenchmarkPair]] = {}
    started = perf_counter()

    for index, document in enumerate(evaluation, start=1):
        record_path = prediction_dir / f"{Path(document.image_name).stem}.json"
        if record_path.exists():
            record = json.loads(record_path.read_text(encoding="utf-8"))
            pairs = [BenchmarkPair.model_validate(pair) for pair in record["pairs"]]
        else:
            pairs = run_tesseract(raw_dir / "images" / document.image_name, executable=executable)
            record_path.write_text(
                json.dumps(
                    {"uid": document.uid, "image_name": document.image_name, "pairs": [pair.model_dump() for pair in pairs]},
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        predictions[document.uid] = pairs
        if index % 10 == 0 or index == len(evaluation):
            print(f"Tesseract {index}/{len(evaluation)}")

    results = {
        "system": "tesseract-chi_sim+eng-regex",
        "documents": len(evaluation),
        "elapsed_seconds": round(perf_counter() - started, 3),
        "metrics": score_by_split(evaluation, predictions),
    }
    results_dir = args.output_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "tesseract.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(results, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
