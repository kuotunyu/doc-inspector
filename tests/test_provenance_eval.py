from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil

import pymupdf
import pytest

from doc_inspector.provenance_eval import (
    GATE_MIN_PAGE_ACCURACY,
    GATE_MIN_VERIFIED_BBOX_HIT_RATE,
    build_extraction,
    comparable_report,
    evaluate_corpus,
    load_corpus,
    verify_corpus_checksums,
)
from scripts_support import load_script_module

ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = ROOT / "data" / "evaluation" / "provenance"
MANIFEST = CORPUS_DIR / "manifest.json"
REPORT = ROOT / "docs" / "assets" / "provenance-evaluation.json"

REQUIRED_CASE_TYPES = {
    "duplicate_same_page",
    "duplicate_across_pages",
    "wrong_claimed_page",
    "hallucinated_evidence",
    "partial_evidence",
    "whitespace_noise",
    "rotated_page",
    "render_resize",
    "nested_list",
    "null_value",
    "image_only_page",
    "claimed_page_out_of_range",
    "line_wrap_join",
    "fuzzy_partial_match",
    "separator_drift",
    "paraphrased_evidence",
    "cross_page_evidence",
}


@pytest.fixture(scope="module")
def corpus():
    return load_corpus(MANIFEST)


@pytest.fixture(scope="module")
def report(corpus):
    return evaluate_corpus(corpus, CORPUS_DIR)


class TestCorpusIntegrity:
    def test_committed_documents_match_their_recorded_checksums(self, corpus) -> None:
        assert verify_corpus_checksums(corpus, CORPUS_DIR) == []

    def test_corpus_is_synthetic_and_versioned(self, corpus) -> None:
        assert corpus.contains_real_personal_data is False
        assert corpus.seed == 20260730
        assert corpus.coordinate_space == "normalized_1000_top_left"
        assert "resolver" in corpus.ground_truth_source
        assert corpus.generator.script == "scripts/build_provenance_corpus.py"

    def test_corpus_is_large_enough_to_be_meaningful(self, corpus) -> None:
        assert corpus.localizable_field_count >= 40
        assert len({document.schema_name for document in corpus.documents}) == 2
        assert any(document.page_count >= 3 for document in corpus.documents)

    def test_every_required_failure_mode_is_represented(self, corpus) -> None:
        case_types = {
            item.case_type
            for document in corpus.documents
            for item in document.fields
        }

        assert REQUIRED_CASE_TYPES <= case_types

    def test_ground_truth_records_pages_rotations_and_boxes(self, corpus) -> None:
        rotations = {
            page.rotation
            for document in corpus.documents
            for page in document.page_geometry
        }
        image_only = [
            page
            for document in corpus.documents
            for page in document.page_geometry
            if page.image_only
        ]
        boxes = [
            item.bbox
            for document in corpus.documents
            for item in document.fields
            if item.bbox is not None
        ]

        assert rotations == {0, 90}
        assert image_only
        assert len(boxes) >= 40
        assert all(box[0] < box[2] and box[1] < box[3] for box in boxes)

    def test_replayed_claims_validate_against_the_product_schema(self, corpus) -> None:
        for document in corpus.documents:
            extraction = build_extraction(document)

            assert extraction.schema_name == document.schema_name


class TestGates:
    def test_no_field_is_ever_falsely_marked_verified(self, report) -> None:
        assert report.metrics.false_verified_rate == 0.0
        assert report.metrics.false_verified_count == 0
        assert [
            outcome.field_path for outcome in report.outcomes if outcome.false_verified
        ] == []

    def test_resolvable_fields_land_on_the_right_page(self, report) -> None:
        assert report.metrics.page_localization_accuracy >= GATE_MIN_PAGE_ACCURACY

    def test_verified_boxes_actually_cover_the_evidence(self, report) -> None:
        assert report.metrics.verified_bbox_hit_rate >= GATE_MIN_VERIFIED_BBOX_HIT_RATE
        assert report.metrics.predicted_bbox_count >= 40

    def test_the_run_reports_itself_as_passing(self, report) -> None:
        assert report.gate_failures == []
        assert report.passed is True
        assert report.corpus_checksums_verified is True

    def test_the_benchmark_never_touches_paid_or_remote_resources(self, report) -> None:
        assert report.uses_network is False
        assert report.uses_api_keys is False
        assert report.uses_gpu is False


class TestHonesty:
    def test_duplicated_evidence_is_reported_as_ambiguous_without_a_box(self, report) -> None:
        duplicates = [
            outcome
            for outcome in report.outcomes
            if outcome.case_type in {"duplicate_same_page", "duplicate_across_pages"}
        ]

        assert duplicates
        assert all(outcome.predicted_status == "ambiguous" for outcome in duplicates)
        assert all(outcome.predicted_bbox is None for outcome in duplicates)
        assert all(outcome.candidate_count >= 2 for outcome in duplicates)

    def test_image_only_pages_degrade_to_page_only(self, report) -> None:
        scanned = [
            outcome for outcome in report.outcomes if outcome.case_type == "image_only_page"
        ]

        assert scanned
        assert all(outcome.predicted_status == "page_only" for outcome in scanned)
        assert all(outcome.resolution_method == "model_claim_only" for outcome in scanned)
        assert all(outcome.predicted_bbox is None for outcome in scanned)

    def test_absent_and_paraphrased_evidence_is_refused(self, report) -> None:
        refused = [
            outcome
            for outcome in report.outcomes
            if outcome.case_type
            in {"hallucinated_evidence", "paraphrased_evidence", "cross_page_evidence"}
        ]

        assert len(refused) == 3
        assert all(outcome.predicted_status == "unresolved" for outcome in refused)
        assert all(outcome.predicted_bbox is None for outcome in refused)

    def test_coverage_is_reported_honestly_rather_than_only_over_easy_fields(
        self,
        report,
    ) -> None:
        metrics = report.metrics

        assert metrics.claimed_field_count > metrics.localizable_field_count
        assert metrics.overall_bbox_coverage < 1.0
        assert metrics.overall_bbox_coverage == pytest.approx(
            round(metrics.predicted_bbox_count / metrics.claimed_field_count, 4)
        )


class TestReproducibility:
    def test_two_runs_agree_field_by_field(self, corpus) -> None:
        first = evaluate_corpus(corpus, CORPUS_DIR)
        second = evaluate_corpus(corpus, CORPUS_DIR)

        assert comparable_report(first) == comparable_report(second)

    def test_the_committed_report_matches_a_fresh_run(self, report) -> None:
        committed = json.loads(REPORT.read_text(encoding="utf-8"))

        assert comparable_report(committed) == comparable_report(report)

    def test_evaluation_never_rewrites_the_ground_truth(self, corpus, tmp_path: Path) -> None:
        staged = tmp_path / "provenance"
        shutil.copytree(CORPUS_DIR, staged)
        before = (staged / "manifest.json").read_bytes()

        evaluate_corpus(load_corpus(staged / "manifest.json"), staged)

        assert (staged / "manifest.json").read_bytes() == before

    def test_the_bundled_font_covers_traditional_chinese(self, corpus) -> None:
        font = pymupdf.Font(corpus.generator.font)

        assert font.name == corpus.generator.font_face
        for character in "補助申請人金額頁證":
            assert font.has_glyph(ord(character)), f"缺少字符：{character}"
        assert font.text_length("補助方案", 12) > 0

    def test_regeneration_reproduces_the_committed_bytes(self, corpus, tmp_path: Path) -> None:
        runtime_face = pymupdf.Font(corpus.generator.font).name
        if (
            pymupdf.VersionBind != corpus.generator.library_version
            or runtime_face != corpus.generator.font_face
        ):
            pytest.skip(
                "PDF bytes are only guaranteed for the recorded PyMuPDF build and font; "
                f"manifest={corpus.generator.library_version}/{corpus.generator.font_face} "
                f"runtime={pymupdf.VersionBind}/{runtime_face}"
            )
        builder = load_script_module("build_provenance_corpus")

        regenerated = builder.build_corpus(tmp_path)

        for document in regenerated["documents"]:
            recorded = next(
                item for item in corpus.documents if item.name == document["name"]
            )
            assert document["sha256"] == recorded.sha256
            assert sha256((tmp_path / document["file"]).read_bytes()).hexdigest() == (
                recorded.sha256
            )

    def test_regenerated_ground_truth_matches_the_committed_manifest(
        self,
        corpus,
        tmp_path: Path,
    ) -> None:
        builder = load_script_module("build_provenance_corpus")

        regenerated = builder.build_corpus(tmp_path)

        for document in regenerated["documents"]:
            recorded = next(
                item for item in corpus.documents if item.name == document["name"]
            )
            recorded_boxes = {item.field_path: item.bbox for item in recorded.fields}
            for item in document["fields"]:
                assert item["bbox"] == recorded_boxes[item["field_path"]]


class TestChecksumFailure:
    def test_a_tampered_document_fails_the_checksum_gate(self, tmp_path: Path) -> None:
        staged = tmp_path / "provenance"
        shutil.copytree(CORPUS_DIR, staged)
        corpus = load_corpus(staged / "manifest.json")
        target = staged / corpus.documents[0].file
        target.write_bytes(target.read_bytes() + b"\n% tampered\n")

        result = evaluate_corpus(load_corpus(staged / "manifest.json"), staged)

        assert result.corpus_checksums_verified is False
        assert result.passed is False
        assert any(failure.startswith("corpus_checksum") for failure in result.gate_failures)
