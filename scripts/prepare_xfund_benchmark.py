"""Create the deterministic XFUND evaluation split and local ground truth."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

from doc_inspector.benchmark import (
    build_evaluation_split,
    load_xfund_documents,
    split_manifest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="準備 XFUND zh 固定評估切分。")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/xfund"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/benchmark"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    raw_dir = args.raw_dir.resolve()
    images_dir = raw_dir / "images"
    train = load_xfund_documents(raw_dir / "zh.train.json", "train_holdout")
    val = load_xfund_documents(raw_dir / "zh.val.json", "val")
    evaluation, prompt_development = build_evaluation_split(train, val)

    missing = [document.image_name for document in [*train, *val] if not (images_dir / document.image_name).is_file()]
    if missing:
        raise SystemExit(f"缺少 {len(missing)} 張 XFUND 圖片。")
    for document in [*train, *val]:
        with Image.open(images_dir / document.image_name) as image:
            image.verify()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = split_manifest(evaluation, prompt_development)
    manifest["raw_manifest"] = str((raw_dir / "manifest.json").name)
    (args.output_dir / "xfund_split.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    ground_truth = {
        document.uid: {
            "source_split": document.source_split,
            "image_name": document.image_name,
            "pairs": [pair.model_dump() for pair in document.ground_truth],
        }
        for document in evaluation
    }
    (args.output_dir / "xfund_ground_truth.json").write_text(
        json.dumps(ground_truth, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    pair_count = sum(len(document.ground_truth) for document in evaluation)
    print(
        json.dumps(
            {
                "evaluation_documents": len(evaluation),
                "val_documents": sum(document.source_split == "val" for document in evaluation),
                "train_holdout_documents": sum(document.source_split == "train_holdout" for document in evaluation),
                "prompt_development_documents": len(prompt_development),
                "ground_truth_pairs": pair_count,
                "images_verified": len(train) + len(val),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
