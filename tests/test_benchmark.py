from __future__ import annotations

from pathlib import Path

from doc_inspector.benchmark import (
    BenchmarkDocument,
    BenchmarkPair,
    build_evaluation_split,
    extract_pairs_from_ocr_text,
    ground_truth_pairs,
    normalize_metric_text,
    score_predictions,
)


def document(uid: str, split: str, pairs: list[tuple[str, str]] | None = None) -> BenchmarkDocument:
    return BenchmarkDocument(
        uid=uid,
        source_split=split,
        image_name=f"{uid}.jpg",
        ground_truth=tuple(BenchmarkPair(key=key, value=value) for key, value in (pairs or [])),
    )


def test_fixed_split_has_50_val_50_holdout_and_99_prompt_documents() -> None:
    train = [document(f"train-{index:03}", "train_holdout") for index in range(149)]
    val = [document(f"val-{index:03}", "val") for index in range(50)]

    evaluation, prompt = build_evaluation_split(train, val)
    evaluation_again, prompt_again = build_evaluation_split(train, val)

    assert len(evaluation) == 100
    assert len(prompt) == 99
    assert [item.uid for item in evaluation] == [item.uid for item in evaluation_again]
    assert [item.uid for item in prompt] == [item.uid for item in prompt_again]
    assert sum(item.source_split == "val" for item in evaluation) == 50


def test_ground_truth_deduplicates_bidirectional_links_and_preserves_duplicate_keys() -> None:
    raw = {
        "document": [
            {"id": 1, "label": "question", "text": "姓名", "linking": [[1, 2], [1, 3]]},
            {"id": 2, "label": "answer", "text": "甲", "linking": [[1, 2]]},
            {"id": 3, "label": "answer", "text": "乙", "linking": [[1, 3]]},
            {"id": 4, "label": "header", "text": "表頭", "linking": []},
        ]
    }

    pairs = ground_truth_pairs(raw)

    assert [(pair.key, pair.value) for pair in pairs] == [("姓名", "甲"), ("姓名", "乙")]


def test_metric_normalization_is_deliberately_narrow() -> None:
    assert normalize_metric_text("  ＡＢＣ\n測試  ") == "abc 測試"
    assert normalize_metric_text("A-B") == "a-b"


def test_duplicate_aware_metrics_match_hand_calculation() -> None:
    docs = [document("one", "val", [("姓名", "甲"), ("姓名", "甲")])]
    predictions = {"one": [BenchmarkPair(key="姓名", value="甲")]}

    score = score_predictions(docs, predictions)

    assert score.reference_pairs == 2
    assert score.predicted_pairs == 1
    assert score.matched_pairs == 1
    assert score.micro_precision == 1.0
    assert score.micro_recall == 0.5
    assert score.micro_f1 == 2 / 3
    assert score.macro_document_f1 == 2 / 3


def test_ocr_regex_baseline_extracts_only_explicit_separators() -> None:
    pairs = extract_pairs_from_ocr_text("姓名：王小明\n金額 = 100\n無分隔文字")

    assert [(pair.key, pair.value) for pair in pairs] == [("姓名", "王小明"), ("金額", "100")]
