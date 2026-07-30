"""Versioned Pydantic schemas used by structured extraction."""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal, Self, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from doc_inspector.errors import ConfigurationError
from doc_inspector.types import ProviderName, SchemaName

SCHEMA_VERSION = "1.1.0"
RULES_VERSION = "1.0.0"
PROVENANCE_VERSION = "1.0.0"

BBOX_SCALE = 1000.0
"""Upper bound of the display-independent bounding-box coordinate space."""


class StrictSchemaModel(BaseModel):
    """Base model that rejects unexpected provider output."""

    model_config = ConfigDict(extra="forbid")


class LocatedValue(StrictSchemaModel):
    """A value plus its one-based source page and short textual evidence."""

    value: str | None = Field(default=None, description="欄位值；無法辨識時為 null，不得猜測")
    page_number: int | None = Field(default=None, ge=1, description="來源頁碼，從 1 開始")
    evidence_text: str | None = Field(
        default=None,
        max_length=300,
        description="支持欄位值的短原文，不要抄錄整頁",
    )


class LocatedIdType(StrictSchemaModel):
    """A normalized identity-document category with source evidence."""

    value: Literal["citizen_id", "resident_id", "passport", "other", "unknown"] | None = None
    page_number: int | None = Field(default=None, ge=1)
    evidence_text: str | None = Field(default=None, max_length=300)


class AdditionalField(StrictSchemaModel):
    """An ordered key-value field not represented by the preset."""

    label: str
    located_value: LocatedValue = Field(default_factory=LocatedValue)


class DocumentPerson(StrictSchemaModel):
    """Applicant or beneficiary identity fields."""

    role: LocatedValue = Field(default_factory=LocatedValue)
    name: LocatedValue = Field(default_factory=LocatedValue)
    id_type: LocatedIdType = Field(
        default_factory=lambda: LocatedIdType(value="unknown")
    )
    id_number: LocatedValue = Field(default_factory=LocatedValue)
    birth_date: LocatedValue = Field(default_factory=LocatedValue)


class ApplicationLineItem(StrictSchemaModel):
    """One requested subsidy amount item."""

    description: LocatedValue = Field(default_factory=LocatedValue)
    amount: LocatedValue = Field(default_factory=LocatedValue)


class SubsidyApplication(StrictSchemaModel):
    """Fixed v1 preset for subsidy application forms."""

    schema_name: Literal["subsidy_application"] = "subsidy_application"
    program_name: LocatedValue = Field(default_factory=LocatedValue)
    application_date: LocatedValue = Field(default_factory=LocatedValue)
    applicants: list[DocumentPerson] = Field(default_factory=list)
    beneficiaries: list[DocumentPerson] = Field(default_factory=list)
    contact_phone: LocatedValue = Field(default_factory=LocatedValue)
    contact_email: LocatedValue = Field(default_factory=LocatedValue)
    address: LocatedValue = Field(default_factory=LocatedValue)
    bank_account_display_name: LocatedValue = Field(default_factory=LocatedValue)
    requested_amount: LocatedValue = Field(default_factory=LocatedValue)
    line_items: list[ApplicationLineItem] = Field(default_factory=list)
    declared_total: LocatedValue = Field(default_factory=LocatedValue)
    additional_fields: list[AdditionalField] = Field(default_factory=list)
    extraction_warnings: list[str] = Field(default_factory=list)


class ReceiptLineItem(StrictSchemaModel):
    """One product or service on a receipt."""

    description: LocatedValue = Field(default_factory=LocatedValue)
    quantity: LocatedValue = Field(default_factory=LocatedValue)
    unit_price: LocatedValue = Field(default_factory=LocatedValue)
    line_total: LocatedValue = Field(default_factory=LocatedValue)


class Receipt(StrictSchemaModel):
    """Fixed v1 preset for receipts and invoices."""

    schema_name: Literal["receipt"] = "receipt"
    merchant_name: LocatedValue = Field(default_factory=LocatedValue)
    receipt_number: LocatedValue = Field(default_factory=LocatedValue)
    receipt_date: LocatedValue = Field(default_factory=LocatedValue)
    currency: LocatedValue = Field(default_factory=LocatedValue)
    line_items: list[ReceiptLineItem] = Field(default_factory=list)
    subtotal: LocatedValue = Field(default_factory=LocatedValue)
    tax: LocatedValue = Field(default_factory=LocatedValue)
    discount: LocatedValue = Field(default_factory=LocatedValue)
    fees: LocatedValue = Field(default_factory=LocatedValue)
    total: LocatedValue = Field(default_factory=LocatedValue)
    additional_fields: list[AdditionalField] = Field(default_factory=list)
    extraction_warnings: list[str] = Field(default_factory=list)


DocumentExtraction: TypeAlias = SubsidyApplication | Receipt
DiscriminatedExtraction = Annotated[DocumentExtraction, Field(discriminator="schema_name")]


class TokenUsage(StrictSchemaModel):
    """Normalized token usage when exposed by the provider."""

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


RuleLevel = Literal["red", "yellow", "green"]


class RuleResult(StrictSchemaModel):
    """One deterministic inspection result with machine-readable evidence."""

    rule_id: str
    level: RuleLevel
    message: str
    field_paths: list[str] = Field(default_factory=list)
    observed: str | None = None
    expected: str | None = None


class ReviewReport(StrictSchemaModel):
    """Completed deterministic review and its strictest overall level."""

    status: Literal["completed"] = "completed"
    overall_level: RuleLevel
    message: str
    checks: list[RuleResult] = Field(default_factory=list)


CoordinateSpace = Literal["normalized_1000_top_left"]
"""Origin at the rendered page's top-left corner; both axes span ``0``–``BBOX_SCALE``."""

VerificationStatus = Literal[
    "verified",
    "approximate",
    "ambiguous",
    "page_only",
    "unresolved",
]
ResolutionMethod = Literal[
    "native_pdf_text",
    "optional_local_ocr",
    "model_claim_only",
    "unavailable",
]


class NormalizedBBox(StrictSchemaModel):
    """A display-independent rectangle on one rendered page.

    Coordinates are expressed in the ``normalized_1000_top_left`` space so that
    render DPI, PDF crop boxes, page rotation, and later image downscaling never
    change the stored numbers.
    """

    x0: float = Field(ge=0.0, le=BBOX_SCALE)
    y0: float = Field(ge=0.0, le=BBOX_SCALE)
    x1: float = Field(ge=0.0, le=BBOX_SCALE)
    y1: float = Field(ge=0.0, le=BBOX_SCALE)

    @model_validator(mode="after")
    def validate_ordering(self) -> Self:
        if not self.x0 < self.x1:
            raise ValueError("bbox 需要 x0 < x1")
        if not self.y0 < self.y1:
            raise ValueError("bbox 需要 y0 < y1")
        return self

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def area(self) -> float:
        return self.width * self.height

    def intersection_area(self, other: NormalizedBBox) -> float:
        """Return the overlapping area, or ``0.0`` when the rectangles are disjoint."""

        overlap_width = min(self.x1, other.x1) - max(self.x0, other.x0)
        overlap_height = min(self.y1, other.y1) - max(self.y0, other.y0)
        if overlap_width <= 0.0 or overlap_height <= 0.0:
            return 0.0
        return overlap_width * overlap_height

    def iou(self, other: NormalizedBBox) -> float:
        """Return intersection-over-union against another rectangle."""

        intersection = self.intersection_area(other)
        union = self.area + other.area - intersection
        return intersection / union if union > 0.0 else 0.0

    def union(self, other: NormalizedBBox) -> NormalizedBBox:
        """Return the smallest rectangle covering both inputs."""

        return NormalizedBBox(
            x0=min(self.x0, other.x0),
            y0=min(self.y0, other.y0),
            x1=max(self.x1, other.x1),
            y1=max(self.y1, other.y1),
        )


class FieldProvenance(StrictSchemaModel):
    """Where one extracted field was actually found in the local document.

    ``claimed_page_number`` and ``evidence_text`` restate the provider claim.
    ``resolved_page_number``, ``bbox``, ``verification_status`` and
    ``match_score`` are produced by deterministic local post-processing and are
    the only fields that may be treated as verified provenance.
    """

    field_path: str
    claimed_page_number: int | None = Field(default=None, ge=1)
    resolved_page_number: int | None = Field(default=None, ge=1)
    evidence_text: str | None = Field(default=None, max_length=300)
    bbox: NormalizedBBox | None = None
    resolution_method: ResolutionMethod
    verification_status: VerificationStatus
    match_score: float | None = Field(default=None, ge=0.0, le=1.0)
    candidate_count: int = Field(default=0, ge=0)
    warning: str | None = None

    @model_validator(mode="after")
    def validate_status_contract(self) -> Self:
        if self.bbox is not None and self.verification_status not in {
            "verified",
            "approximate",
        }:
            raise ValueError("只有 verified 或 approximate 才能帶 bbox")
        if self.bbox is not None and self.resolved_page_number is None:
            raise ValueError("帶 bbox 時必須有 resolved_page_number")
        if self.verification_status in {"verified", "approximate"} and self.bbox is None:
            raise ValueError("verified 或 approximate 必須提供 bbox")
        if self.verification_status == "verified" and self.resolution_method not in {
            "native_pdf_text",
            "optional_local_ocr",
        }:
            raise ValueError("verified 只能來自本機文字層或本機 OCR")
        if self.resolution_method == "model_claim_only" and self.bbox is not None:
            raise ValueError("model_claim_only 不得產生 bbox")
        return self


class ProvenanceSummary(StrictSchemaModel):
    """Counts per verification status for quick UI and export summaries."""

    field_count: int = Field(default=0, ge=0)
    verified: int = Field(default=0, ge=0)
    approximate: int = Field(default=0, ge=0)
    ambiguous: int = Field(default=0, ge=0)
    page_only: int = Field(default=0, ge=0)
    unresolved: int = Field(default=0, ge=0)


class ProvenanceCollection(StrictSchemaModel):
    """Versioned, additive provenance payload attached to an inspection."""

    provenance_version: str = PROVENANCE_VERSION
    coordinate_space: CoordinateSpace = "normalized_1000_top_left"
    coordinate_scale: float = BBOX_SCALE
    text_layer_pages: int = Field(default=0, ge=0)
    ocr_pages: int = Field(default=0, ge=0)
    fields: list[FieldProvenance] = Field(default_factory=list)
    summary: ProvenanceSummary = Field(default_factory=ProvenanceSummary)


class InspectionBundle(StrictSchemaModel):
    """Safe service output without source paths or raw provider payloads."""

    schema_version: str = SCHEMA_VERSION
    rules_version: str = RULES_VERSION
    provider: ProviderName
    model: str
    source_file_name: str
    page_count: int = Field(ge=1)
    elapsed_ms: int = Field(ge=0)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    extraction: DiscriminatedExtraction
    warnings: list[str] = Field(default_factory=list)
    review_report: ReviewReport = Field(default_factory=ReviewReport)
    provenance: ProvenanceCollection | None = None


SchemaModel: TypeAlias = type[SubsidyApplication] | type[Receipt]


class SchemaRegistry:
    """Explicit registry for the two supported v1 schema presets."""

    _models: ClassVar[dict[SchemaName, SchemaModel]] = {
        "subsidy_application": SubsidyApplication,
        "receipt": Receipt,
    }

    @classmethod
    def get(cls, name: SchemaName) -> SchemaModel:
        try:
            return cls._models[name]
        except KeyError as exc:
            raise ConfigurationError(f"不支援的 schema：{name!r}。") from exc

    @classmethod
    def names(cls) -> tuple[SchemaName, ...]:
        return tuple(cls._models)
