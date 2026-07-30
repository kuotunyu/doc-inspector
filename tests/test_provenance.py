from __future__ import annotations

import json

import pytest

from doc_inspector.ingest import (
    DocumentTextLayer,
    NormalizedPage,
    PageTextLayer,
    PageToken,
)
from doc_inspector.provenance import (
    build_match_index,
    iter_located_fields,
    normalize_match_text,
    resolve_field_provenance,
    resolve_provenance,
    search_evidence,
)
from doc_inspector.rules import inspect_extraction
from doc_inspector.schemas import (
    AdditionalField,
    ApplicationLineItem,
    DocumentPerson,
    FieldProvenance,
    InspectionBundle,
    LocatedIdType,
    LocatedValue,
    NormalizedBBox,
    Receipt,
    ReceiptLineItem,
    SubsidyApplication,
)


def line_tokens(text: str, *, row: int, confidence: float | None = None) -> list[PageToken]:
    """Lay out one glyph per 20 units on a synthetic row, mirroring native extraction."""

    tokens = []
    for column, character in enumerate(text):
        if character.isspace():
            continue
        tokens.append(
            PageToken(
                text=character,
                bbox=NormalizedBBox(
                    x0=10.0 + column * 20.0,
                    y0=40.0 * row,
                    x1=10.0 + column * 20.0 + 18.0,
                    y1=40.0 * row + 30.0,
                ),
                confidence=confidence,
            )
        )
    return tokens


def text_page(page_number: int, *lines: str, source: str = "native_pdf_text", confidence: float | None = None) -> PageTextLayer:
    tokens: list[PageToken] = []
    for row, line in enumerate(lines, start=1):
        tokens.extend(line_tokens(line, row=row, confidence=confidence))
    return PageTextLayer(page_number=page_number, source=source, tokens=tuple(tokens))


def layer(*pages: PageTextLayer) -> DocumentTextLayer:
    return DocumentTextLayer(pages=tuple(pages))


def resolve(located: LocatedValue, document: DocumentTextLayer, **kwargs) -> FieldProvenance:
    return resolve_field_provenance(
        "field",
        located,
        build_match_index(document),
        page_count=len(document.pages) or None,
        **kwargs,
    )


class TestNormalizedBBox:
    def test_rejects_degenerate_and_inverted_rectangles(self) -> None:
        with pytest.raises(ValueError, match="x0 < x1"):
            NormalizedBBox(x0=100.0, y0=10.0, x1=100.0, y1=50.0)
        with pytest.raises(ValueError, match="y0 < y1"):
            NormalizedBBox(x0=10.0, y0=90.0, x1=50.0, y1=20.0)

    def test_rejects_coordinates_outside_the_declared_space(self) -> None:
        with pytest.raises(ValueError):
            NormalizedBBox(x0=-1.0, y0=10.0, x1=50.0, y1=20.0)
        with pytest.raises(ValueError):
            NormalizedBBox(x0=10.0, y0=10.0, x1=1001.0, y1=20.0)

    def test_iou_and_union_are_geometrically_correct(self) -> None:
        left = NormalizedBBox(x0=0.0, y0=0.0, x1=100.0, y1=100.0)
        right = NormalizedBBox(x0=50.0, y0=0.0, x1=150.0, y1=100.0)

        assert left.iou(left) == pytest.approx(1.0)
        assert left.iou(right) == pytest.approx(5000 / 15000)
        assert left.iou(NormalizedBBox(x0=200.0, y0=0.0, x1=300.0, y1=100.0)) == 0.0
        assert left.union(right).model_dump() == {
            "x0": 0.0,
            "y0": 0.0,
            "x1": 150.0,
            "y1": 100.0,
        }


class TestFieldProvenanceContract:
    def test_unverifiable_statuses_can_never_carry_a_bounding_box(self) -> None:
        box = NormalizedBBox(x0=1.0, y0=1.0, x1=2.0, y1=2.0)
        for status in ("ambiguous", "page_only", "unresolved"):
            with pytest.raises(ValueError, match="verified 或 approximate"):
                FieldProvenance(
                    field_path="x",
                    resolved_page_number=1,
                    bbox=box,
                    resolution_method="native_pdf_text",
                    verification_status=status,
                )

    def test_located_statuses_require_a_box_and_a_page(self) -> None:
        with pytest.raises(ValueError, match="必須提供 bbox"):
            FieldProvenance(
                field_path="x",
                resolution_method="native_pdf_text",
                verification_status="verified",
            )
        with pytest.raises(ValueError, match="resolved_page_number"):
            FieldProvenance(
                field_path="x",
                bbox=NormalizedBBox(x0=1.0, y0=1.0, x1=2.0, y1=2.0),
                resolution_method="native_pdf_text",
                verification_status="verified",
            )

    def test_model_claims_can_never_be_marked_verified(self) -> None:
        with pytest.raises(ValueError, match="verified 只能來自"):
            FieldProvenance(
                field_path="x",
                resolved_page_number=1,
                bbox=NormalizedBBox(x0=1.0, y0=1.0, x1=2.0, y1=2.0),
                resolution_method="model_claim_only",
                verification_status="verified",
            )


class TestNormalization:
    def test_only_documented_transformations_are_applied(self) -> None:
        assert normalize_match_text("１２３ ＡＢ") == "123ab"
        assert normalize_match_text("測 試\n文\t件") == "測試文件"
        assert normalize_match_text("soft­hyphen​zero") == "softhyphenzero"
        assert normalize_match_text("Mixed CASE") == "mixedcase"

    def test_hyphens_are_preserved_so_identifiers_stay_distinct(self) -> None:
        assert normalize_match_text("DEMO-PASSPORT-001") == "demo-passport-001"
        assert normalize_match_text("DEMOPASSPORT001") != normalize_match_text(
            "DEMO-PASSPORT-001"
        )


class TestEvidenceMatching:
    def test_unique_exact_match_on_the_claimed_page_is_verified(self) -> None:
        document = layer(text_page(1, "補助方案：安心生活", "申請日期：2026-07-23"))

        result = resolve(
            LocatedValue(value="2026-07-23", page_number=1, evidence_text="申請日期：2026-07-23"),
            document,
        )

        assert result.verification_status == "verified"
        assert result.resolution_method == "native_pdf_text"
        assert result.resolved_page_number == 1
        assert result.match_score == 1.0
        assert result.candidate_count == 1
        assert result.bbox is not None
        assert result.warning is None

    def test_repeated_evidence_on_one_page_is_ambiguous_and_keeps_the_page(self) -> None:
        document = layer(text_page(1, "重複標記ABC", "其他內容", "重複標記ABC"))

        result = resolve(
            LocatedValue(value="重複標記", page_number=1, evidence_text="重複標記ABC"),
            document,
        )

        assert result.verification_status == "ambiguous"
        assert result.bbox is None
        assert result.candidate_count == 2
        assert result.resolved_page_number == 1
        assert "同一頁" in (result.warning or "")

    def test_repeated_evidence_across_pages_refuses_to_name_a_page(self) -> None:
        document = layer(text_page(1, "跨頁標記XY"), text_page(2, "跨頁標記XY"))

        result = resolve(
            LocatedValue(value="跨頁標記", page_number=1, evidence_text="跨頁標記XY"),
            document,
        )

        assert result.verification_status == "ambiguous"
        assert result.bbox is None
        assert result.resolved_page_number is None
        assert result.candidate_count == 2
        assert "跨多頁" in (result.warning or "")

    def test_a_wrong_page_claim_downgrades_to_approximate_with_the_real_page(self) -> None:
        document = layer(text_page(1, "第一頁內容"), text_page(2, "申請金額：1,200"))

        result = resolve(
            LocatedValue(value="1200", page_number=1, evidence_text="申請金額：1,200"),
            document,
        )

        assert result.verification_status == "approximate"
        assert result.claimed_page_number == 1
        assert result.resolved_page_number == 2
        assert result.bbox is not None
        assert "模型宣稱第 1 頁" in (result.warning or "")

    def test_missing_evidence_is_unresolved_rather_than_guessed(self) -> None:
        document = layer(text_page(1, "文件實際內容"))

        result = resolve(
            LocatedValue(value="X", page_number=1, evidence_text="模型幻覺出來的字串"),
            document,
        )

        assert result.verification_status == "unresolved"
        assert result.bbox is None
        assert result.resolved_page_number is None
        assert result.candidate_count == 0

    def test_conservative_partial_match_is_approximate_and_scored(self) -> None:
        document = layer(text_page(1, "申請人姓名：測試申請人甲"))

        result = resolve(
            LocatedValue(
                value="測試申請人乙",
                page_number=1,
                evidence_text="申請人姓名：測試申請人乙",
            ),
            document,
        )

        assert result.verification_status == "approximate"
        assert result.match_score is not None
        assert 0.6 <= result.match_score < 1.0
        assert result.bbox is not None
        assert "部分相符" in (result.warning or "")

    def test_short_evidence_is_matched_exactly_or_not_at_all(self) -> None:
        document = layer(text_page(1, "金額 1200"))

        result = resolve(
            LocatedValue(value="1300", page_number=1, evidence_text="1300"),
            document,
        )

        assert result.verification_status == "unresolved"
        assert result.bbox is None

    def test_weak_partial_overlap_is_rejected(self) -> None:
        document = layer(text_page(1, "完全不同的一段文字內容在這裡"))

        result = search_evidence(
            build_match_index(document),
            normalize_match_text("申請人姓名：測試申請人甲乙丙丁"),
        )

        assert result.candidates == ()
        assert result.score is None

    def test_line_wrapped_evidence_joins_without_stripping_hyphens(self) -> None:
        document = layer(text_page(1, "撥款帳戶名稱：測試申請", "人甲專戶"))

        result = resolve(
            LocatedValue(
                value="測試申請人甲專戶",
                page_number=1,
                evidence_text="撥款帳戶名稱：測試申請\n人甲專戶",
            ),
            document,
        )

        assert result.verification_status == "verified"
        assert result.bbox is not None
        assert result.bbox.y1 > result.bbox.y0


class TestFallbackPolicy:
    def test_page_without_text_layer_degrades_to_page_only(self) -> None:
        document = layer(PageTextLayer(page_number=1), PageTextLayer(page_number=2))

        result = resolve(
            LocatedValue(value="452", page_number=2, evidence_text="應付總額：452"),
            document,
        )

        assert result.verification_status == "page_only"
        assert result.resolution_method == "model_claim_only"
        assert result.resolved_page_number == 2
        assert result.bbox is None
        assert "尚未經本機驗證" in (result.warning or "")

    def test_claimed_page_beyond_the_document_is_unresolved(self) -> None:
        document = layer(text_page(1, "只有一頁"))

        result = resolve(
            LocatedValue(value="X", page_number=9, evidence_text="任何內容"),
            document,
        )

        assert result.verification_status == "unresolved"
        assert "超出文件頁數" in (result.warning or "")

    def test_empty_claim_is_unresolved_and_unavailable(self) -> None:
        document = layer(text_page(1, "有文字層"))

        result = resolve(LocatedValue(), document)

        assert result.verification_status == "unresolved"
        assert result.resolution_method == "unavailable"

    def test_value_is_used_only_as_a_capped_fallback_for_missing_evidence(self) -> None:
        document = layer(text_page(1, "申請人姓名：測試申請人甲"))

        result = resolve(
            LocatedValue(value="測試申請人甲", page_number=1, evidence_text=None),
            document,
        )

        assert result.verification_status == "approximate"
        assert result.bbox is not None
        assert "改以欄位值" in (result.warning or "")


class TestOptionalOcr:
    class FakeOcr:
        def __init__(self, confidence: float) -> None:
            self.confidence = confidence

        def page_tokens(self, page: NormalizedPage) -> tuple[PageToken, ...]:
            return tuple(
                token
                for row, line in enumerate(["應付總額：452"], start=1)
                for token in line_tokens(line, row=row, confidence=self.confidence)
            )

    class FailingOcr:
        def page_tokens(self, page: NormalizedPage) -> tuple[PageToken, ...]:
            raise RuntimeError("tesseract 不存在")

    def _document(self) -> tuple[Receipt, DocumentTextLayer, tuple[NormalizedPage, ...]]:
        extraction = Receipt(
            total=LocatedValue(value="452", page_number=1, evidence_text="應付總額：452")
        )
        pages = (NormalizedPage(page_number=1, data=b"", width=100, height=100),)
        return extraction, layer(PageTextLayer(page_number=1)), pages

    def test_high_confidence_ocr_can_verify(self) -> None:
        extraction, text_layer, pages = self._document()

        collection = resolve_provenance(
            extraction,
            text_layer,
            pages=pages,
            ocr_provider=self.FakeOcr(confidence=95.0),
        )
        total = next(item for item in collection.fields if item.field_path == "total")

        assert total.verification_status == "verified"
        assert total.resolution_method == "optional_local_ocr"
        assert collection.ocr_pages == 1

    def test_low_confidence_ocr_is_capped_at_approximate(self) -> None:
        extraction, text_layer, pages = self._document()

        collection = resolve_provenance(
            extraction,
            text_layer,
            pages=pages,
            ocr_provider=self.FakeOcr(confidence=45.0),
        )
        total = next(item for item in collection.fields if item.field_path == "total")

        assert total.verification_status == "approximate"
        assert "辨識信心未達門檻" in (total.warning or "")

    def test_a_broken_ocr_extra_never_aborts_the_review(self) -> None:
        extraction, text_layer, pages = self._document()

        collection = resolve_provenance(
            extraction,
            text_layer,
            pages=pages,
            ocr_provider=self.FailingOcr(),
        )
        total = next(item for item in collection.fields if item.field_path == "total")

        assert total.verification_status == "page_only"
        assert collection.ocr_pages == 0


class TestFieldTraversal:
    def test_every_located_field_gets_a_stable_dotted_path(self) -> None:
        extraction = SubsidyApplication(
            applicants=[DocumentPerson(), DocumentPerson()],
            beneficiaries=[DocumentPerson()],
            line_items=[ApplicationLineItem(), ApplicationLineItem(), ApplicationLineItem()],
            additional_fields=[
                AdditionalField(label="甲"),
                AdditionalField(label="乙"),
            ],
        )

        paths = [path for path, _ in iter_located_fields(extraction)]

        assert paths[0] == "program_name"
        assert "applicants.0.name" in paths
        assert "applicants.1.id_type" in paths
        assert "beneficiaries.0.birth_date" in paths
        assert "line_items.2.amount" in paths
        assert "additional_fields.1.located_value" in paths
        assert len(paths) == len(set(paths))
        assert paths == [path for path, _ in iter_located_fields(extraction)]

    def test_traversal_covers_identity_types_and_receipt_line_items(self) -> None:
        extraction = Receipt(line_items=[ReceiptLineItem()])

        located = dict(iter_located_fields(extraction))

        assert "line_items.0.unit_price" in located
        assert "extraction_warnings" not in located
        assert "schema_name" not in located

    def test_identity_type_fields_are_resolved_like_other_claims(self) -> None:
        document = layer(text_page(1, "證件種類：國民身分證"))

        result = resolve_field_provenance(
            "applicants.0.id_type",
            LocatedIdType(
                value="citizen_id",
                page_number=1,
                evidence_text="證件種類：國民身分證",
            ),
            build_match_index(document),
            page_count=1,
        )

        assert result.verification_status == "verified"
        assert result.field_path == "applicants.0.id_type"


class TestCollection:
    def test_summary_counts_every_status(self) -> None:
        extraction = Receipt(
            merchant_name=LocatedValue(value="A", page_number=1, evidence_text="店家：甲商店"),
            receipt_date=LocatedValue(value="B", page_number=1, evidence_text="不存在的一段文字"),
            total=LocatedValue(value="C", page_number=1, evidence_text="重複片語ZZ"),
        )
        document = layer(text_page(1, "店家：甲商店", "重複片語ZZ", "重複片語ZZ"))

        collection = resolve_provenance(extraction, document)
        by_path = {item.field_path: item for item in collection.fields}

        assert collection.provenance_version == "1.0.0"
        assert collection.coordinate_space == "normalized_1000_top_left"
        assert collection.text_layer_pages == 1
        assert by_path["merchant_name"].verification_status == "verified"
        assert by_path["receipt_date"].verification_status == "unresolved"
        assert by_path["total"].verification_status == "ambiguous"
        assert collection.summary.field_count == len(collection.fields)
        assert collection.summary.verified == 1
        assert collection.summary.ambiguous == 1


class TestBackwardCompatibility:
    def test_a_v1_0_bundle_without_provenance_still_validates(self) -> None:
        legacy = {
            "schema_version": "1.0.0",
            "rules_version": "1.0.0",
            "provider": "gemini",
            "model": "legacy-model",
            "source_file_name": "legacy.png",
            "page_count": 1,
            "elapsed_ms": 12,
            "extraction": {"schema_name": "receipt"},
            "review_report": {
                "status": "completed",
                "overall_level": "red",
                "message": "檢核完成：紅 1、黃 0、綠 0。",
                "checks": [],
            },
        }

        bundle = InspectionBundle.model_validate(legacy)

        assert bundle.provenance is None
        assert bundle.schema_version == "1.0.0"
        assert json.loads(bundle.model_dump_json())["provenance"] is None

    def test_provenance_round_trips_through_json(self) -> None:
        extraction = Receipt(
            merchant_name=LocatedValue(value="甲", page_number=1, evidence_text="店家：甲商店")
        )
        bundle = InspectionBundle(
            provider="openai",
            model="m",
            source_file_name="x.pdf",
            page_count=1,
            elapsed_ms=1,
            extraction=extraction,
            review_report=inspect_extraction(extraction),
            provenance=resolve_provenance(extraction, layer(text_page(1, "店家：甲商店"))),
        )

        restored = InspectionBundle.model_validate_json(bundle.model_dump_json())

        assert restored.provenance is not None
        assert restored.provenance == bundle.provenance
