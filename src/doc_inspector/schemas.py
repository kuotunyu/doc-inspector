"""Versioned Pydantic schemas used by structured extraction."""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from doc_inspector.errors import ConfigurationError
from doc_inspector.types import ProviderName, SchemaName

SCHEMA_VERSION = "1.0.0"
RULES_VERSION = "1.0.0"


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
