"""Deterministic verification of provider evidence claims against local text.

The extraction schema stores what the model *claimed*: a value, a page number,
and a short evidence string. Nothing in that payload proves the evidence exists
in the uploaded document. This module performs local, deterministic
post-processing that either locates the claimed evidence in the document's own
text layer, or states plainly that it could not. It never invents a bounding box.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from math import ceil
from typing import Protocol
import unicodedata

from pydantic import BaseModel

from doc_inspector.ingest import (
    DocumentTextLayer,
    NormalizedPage,
    PageTextLayer,
    PageToken,
)
from doc_inspector.schemas import (
    DocumentExtraction,
    FieldProvenance,
    LocatedIdType,
    LocatedValue,
    NormalizedBBox,
    ProvenanceCollection,
    ProvenanceSummary,
    ResolutionMethod,
    VerificationStatus,
)

MIN_PARTIAL_CHARACTERS = 4
"""A partial match shorter than this is treated as coincidence, not evidence."""

MIN_PARTIAL_RATIO = 0.6
"""A partial match must cover at least this share of the normalized evidence."""

MIN_PARTIAL_NEEDLE_LENGTH = 6
"""Short evidence strings are matched exactly or not at all."""

OCR_VERIFIED_CONFIDENCE = 80.0
"""Every matched OCR word must reach this confidence before a claim is verified."""

_INVISIBLE_CHARACTERS = frozenset(
    {
        "\u00ad",  # soft hyphen
        "\u200b",  # zero width space
        "\u200c",  # zero width non-joiner
        "\u200d",  # zero width joiner
        "\u2060",  # word joiner
        "\ufeff",  # zero width no-break space
    }
)

_SKIPPED_MODEL_FIELDS = frozenset({"schema_name", "extraction_warnings"})


class EvidenceOcrProvider(Protocol):
    """Optional local OCR used only for pages without a native text layer."""

    def page_tokens(self, page: NormalizedPage) -> Sequence[PageToken]: ...


def normalize_match_text(text: str) -> str:
    """Apply the documented, lossless-enough normalization used for matching.

    Only three transformations are performed, all of them reversible in meaning:
    Unicode NFKC, case folding, and removal of whitespace plus zero-width
    joiners. Removing whitespace is what makes line wraps and doubled spaces
    harmless. Hyphens are deliberately preserved, because stripping them would
    silently merge distinct identifiers.
    """

    folded = unicodedata.normalize("NFKC", text)
    return "".join(
        character.casefold()
        for character in folded
        if not character.isspace() and character not in _INVISIBLE_CHARACTERS
    )


@dataclass(frozen=True, slots=True)
class EvidenceCandidate:
    """One distinct region of a page that matches the searched evidence."""

    page_number: int
    source: str
    token_indices: tuple[int, ...]
    bbox: NormalizedBBox
    min_confidence: float | None


@dataclass(frozen=True, slots=True)
class EvidenceSearchResult:
    """Outcome of searching one normalized evidence string across a document."""

    candidates: tuple[EvidenceCandidate, ...]
    needle_length: int
    matched_characters: int
    exact: bool

    @property
    def score(self) -> float | None:
        if not self.candidates or self.needle_length <= 0:
            return None
        return round(min(1.0, self.matched_characters / self.needle_length), 4)


@dataclass(frozen=True, slots=True)
class _PageIndex:
    """Searchable projection of one page's positioned words."""

    layer: PageTextLayer
    text: str
    owners: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class MatchIndex:
    """Reusable search structure built once per document."""

    pages: tuple[_PageIndex, ...]

    @property
    def has_text(self) -> bool:
        return any(page.text for page in self.pages)

    @property
    def text_page_numbers(self) -> tuple[int, ...]:
        return tuple(page.layer.page_number for page in self.pages if page.text)

    def page(self, page_number: int) -> _PageIndex | None:
        for candidate in self.pages:
            if candidate.layer.page_number == page_number:
                return candidate
        return None

    def primary_method(self) -> ResolutionMethod:
        """Return the method that best describes what was actually searched."""

        sources = {page.layer.source for page in self.pages if page.text}
        if "native_pdf_text" in sources:
            return "native_pdf_text"
        if "optional_local_ocr" in sources:
            return "optional_local_ocr"
        return "unavailable"


def build_match_index(text_layer: DocumentTextLayer) -> MatchIndex:
    """Project every page's words into a normalized, position-mapped string."""

    pages: list[_PageIndex] = []
    for layer in text_layer.pages:
        characters: list[str] = []
        owners: list[int] = []
        for index, token in enumerate(layer.tokens):
            for character in normalize_match_text(token.text):
                characters.append(character)
                owners.append(index)
        pages.append(
            _PageIndex(layer=layer, text="".join(characters), owners=tuple(owners))
        )
    return MatchIndex(pages=tuple(pages))


def _find_all(haystack: str, needle: str) -> list[int]:
    """Return every start offset of ``needle``, including overlapping matches."""

    if not needle or not haystack:
        return []
    offsets: list[int] = []
    position = haystack.find(needle)
    while position != -1:
        offsets.append(position)
        position = haystack.find(needle, position + 1)
    return offsets


def _candidate_from_span(
    page: _PageIndex,
    start: int,
    length: int,
) -> EvidenceCandidate | None:
    indices = sorted(set(page.owners[start : start + length]))
    if not indices:
        return None
    tokens = [page.layer.tokens[index] for index in indices]
    bbox = tokens[0].bbox
    for token in tokens[1:]:
        bbox = bbox.union(token.bbox)
    confidences = [token.confidence for token in tokens]
    min_confidence = (
        min(value for value in confidences if value is not None)
        if all(value is not None for value in confidences)
        else None
    )
    return EvidenceCandidate(
        page_number=page.layer.page_number,
        source=page.layer.source,
        token_indices=tuple(indices),
        bbox=bbox,
        min_confidence=min_confidence,
    )


def _collect(index: MatchIndex, needle: str, length: int) -> list[EvidenceCandidate]:
    """Return distinct candidate regions for every substring of the given length."""

    grams = {needle[offset : offset + length] for offset in range(len(needle) - length + 1)}
    candidates: list[EvidenceCandidate] = []
    seen: set[tuple[int, tuple[int, ...]]] = set()
    for page in index.pages:
        if not page.text:
            continue
        for gram in sorted(grams):
            for start in _find_all(page.text, gram):
                candidate = _candidate_from_span(page, start, length)
                if candidate is None:
                    continue
                identity = (candidate.page_number, candidate.token_indices)
                if identity in seen:
                    continue
                seen.add(identity)
                candidates.append(candidate)
    candidates.sort(key=lambda item: (item.page_number, item.token_indices))
    return candidates


def _shares_substring(index: MatchIndex, needle: str, length: int) -> bool:
    if length <= 0 or length > len(needle):
        return False
    grams = {needle[offset : offset + length] for offset in range(len(needle) - length + 1)}
    for page in index.pages:
        if len(page.text) < length:
            continue
        page_grams = {
            page.text[offset : offset + length]
            for offset in range(len(page.text) - length + 1)
        }
        if grams & page_grams:
            return True
    return False


def search_evidence(
    index: MatchIndex,
    needle: str,
    *,
    min_partial_characters: int = MIN_PARTIAL_CHARACTERS,
    min_partial_ratio: float = MIN_PARTIAL_RATIO,
    min_partial_needle_length: int = MIN_PARTIAL_NEEDLE_LENGTH,
) -> EvidenceSearchResult:
    """Search a normalized evidence string, exactly first and then conservatively."""

    needle_length = len(needle)
    if not needle_length or not index.has_text:
        return EvidenceSearchResult((), needle_length, 0, False)

    exact = _collect(index, needle, needle_length)
    if exact:
        return EvidenceSearchResult(tuple(exact), needle_length, needle_length, True)

    if needle_length < min_partial_needle_length:
        return EvidenceSearchResult((), needle_length, 0, False)

    floor = max(min_partial_characters, ceil(min_partial_ratio * needle_length))
    if floor > needle_length:
        return EvidenceSearchResult((), needle_length, 0, False)

    best = 0
    low, high = floor, needle_length - 1
    while low <= high:
        middle = (low + high) // 2
        if _shares_substring(index, needle, middle):
            best = middle
            low = middle + 1
        else:
            high = middle - 1
    if best < floor:
        return EvidenceSearchResult((), needle_length, 0, False)
    return EvidenceSearchResult(
        tuple(_collect(index, needle, best)), needle_length, best, False
    )


def iter_located_fields(
    extraction: DocumentExtraction,
) -> Iterator[tuple[str, LocatedValue | LocatedIdType]]:
    """Yield every located field with a stable, export-safe dotted path.

    Ordering follows Pydantic field declaration order and list index, so a path
    such as ``applicants.0.name`` or ``line_items.2.amount`` never depends on UI
    sorting. The dotted form matches ``RuleResult.field_paths``, which lets a
    check and its provenance be joined without translation.
    """

    yield from _walk_located(extraction, "")


def _walk_located(
    value: object,
    path: str,
) -> Iterator[tuple[str, LocatedValue | LocatedIdType]]:
    if isinstance(value, (LocatedValue, LocatedIdType)):
        yield path, value
    elif isinstance(value, BaseModel):
        for field_name in type(value).model_fields:
            if field_name in _SKIPPED_MODEL_FIELDS:
                continue
            child_path = f"{path}.{field_name}" if path else field_name
            yield from _walk_located(getattr(value, field_name), child_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            child_path = f"{path}.{index}" if path else str(index)
            yield from _walk_located(item, child_path)


def _claim_text(located: LocatedValue | LocatedIdType) -> str:
    return (located.value or "").strip() if located.value is not None else ""


def _unlocated(
    field_path: str,
    located: LocatedValue | LocatedIdType,
    *,
    status: VerificationStatus,
    method: ResolutionMethod,
    warning: str,
    resolved_page: int | None = None,
    candidate_count: int = 0,
) -> FieldProvenance:
    return FieldProvenance(
        field_path=field_path,
        claimed_page_number=located.page_number,
        resolved_page_number=resolved_page,
        evidence_text=located.evidence_text,
        bbox=None,
        resolution_method=method,
        verification_status=status,
        match_score=None,
        candidate_count=candidate_count,
        warning=warning,
    )


def resolve_field_provenance(
    field_path: str,
    located: LocatedValue | LocatedIdType,
    index: MatchIndex,
    *,
    page_count: int | None = None,
    min_partial_characters: int = MIN_PARTIAL_CHARACTERS,
    min_partial_ratio: float = MIN_PARTIAL_RATIO,
    ocr_verified_confidence: float = OCR_VERIFIED_CONFIDENCE,
) -> FieldProvenance:
    """Verify one provider claim against the local text layer."""

    claimed = located.page_number
    claimed_layer = index.page(claimed) if claimed is not None else None
    claimed_page_missing = (
        claimed is not None
        and claimed_layer is None
        and page_count is not None
        and claimed > page_count
    )

    evidence = (located.evidence_text or "").strip()
    value_text = _claim_text(located)
    used_value_fallback = not evidence and bool(value_text)
    needle = normalize_match_text(evidence or value_text)

    if not needle:
        return _unlocated(
            field_path,
            located,
            status="unresolved",
            method="unavailable",
            warning="模型沒有提供可核驗的欄位值或證據原文。",
        )

    result = search_evidence(
        index,
        needle,
        min_partial_characters=min_partial_characters,
        min_partial_ratio=min_partial_ratio,
    )
    candidates = result.candidates

    if len(candidates) > 1:
        pages = {candidate.page_number for candidate in candidates}
        resolved_page = pages.pop() if len(pages) == 1 else None
        scope = "同一頁" if resolved_page is not None else "跨多頁"
        return _unlocated(
            field_path,
            located,
            status="ambiguous",
            method=candidates[0].source,  # type: ignore[arg-type]
            warning=(
                f"這段證據在文件中{scope}出現 {len(candidates)} 次，"
                "無法唯一定位，因此不提供位置。"
            ),
            resolved_page=resolved_page,
            candidate_count=len(candidates),
        )

    if not candidates:
        if claimed_page_missing:
            return _unlocated(
                field_path,
                located,
                status="unresolved",
                method="unavailable",
                warning=f"模型宣稱的第 {claimed} 頁超出文件頁數，無法核驗。",
            )
        if claimed is not None and (claimed_layer is None or not claimed_layer.text):
            return _unlocated(
                field_path,
                located,
                status="page_only",
                method="model_claim_only",
                warning=(
                    "這一頁沒有可用的本機文字層；頁碼來自模型，"
                    "位置尚未經本機驗證。"
                ),
                resolved_page=claimed,
            )
        if not index.has_text:
            return _unlocated(
                field_path,
                located,
                status="unresolved",
                method="unavailable",
                warning="本機沒有可用的文字層，也沒有頁碼宣稱，無法核驗來源。",
            )
        return _unlocated(
            field_path,
            located,
            status="unresolved",
            method=index.primary_method(),
            warning="在本機文字層找不到這段證據；請人工回原文件確認。",
        )

    candidate = candidates[0]
    warnings: list[str] = []
    status: VerificationStatus = "verified"

    if used_value_fallback:
        status = "approximate"
        warnings.append("模型沒有提供證據原文，改以欄位值在文件中定位。")
    if not result.exact:
        status = "approximate"
        warnings.append(
            f"只比對到 {result.matched_characters}/{result.needle_length} 個字元，"
            "屬於部分相符。"
        )
    if claimed is not None and claimed != candidate.page_number:
        status = "approximate"
        warnings.append(
            f"模型宣稱第 {claimed} 頁，本機只在第 {candidate.page_number} 頁找到這段證據。"
        )
    if candidate.source == "optional_local_ocr":
        confidence = candidate.min_confidence
        if confidence is None or confidence < ocr_verified_confidence:
            status = "approximate"
            warnings.append(
                "位置來自本機 OCR，且辨識信心未達門檻，僅供參考。"
            )

    return FieldProvenance(
        field_path=field_path,
        claimed_page_number=claimed,
        resolved_page_number=candidate.page_number,
        evidence_text=located.evidence_text,
        bbox=candidate.bbox,
        resolution_method=candidate.source,  # type: ignore[arg-type]
        verification_status=status,
        match_score=result.score,
        candidate_count=1,
        warning="；".join(warnings) or None,
    )


def _ocr_augmented_layer(
    text_layer: DocumentTextLayer,
    pages: Sequence[NormalizedPage],
    provider: EvidenceOcrProvider,
) -> DocumentTextLayer:
    """Fill pages without native text using optional local OCR, never failing hard."""

    by_number = {page.page_number: page for page in pages}
    augmented: list[PageTextLayer] = []
    for layer in text_layer.pages:
        page = by_number.get(layer.page_number)
        if layer.has_text or page is None:
            augmented.append(layer)
            continue
        try:
            tokens = tuple(provider.page_tokens(page))
        except Exception:  # noqa: BLE001 - optional dependency must never abort review
            augmented.append(layer)
            continue
        if not tokens:
            augmented.append(layer)
            continue
        augmented.append(
            PageTextLayer(
                page_number=layer.page_number,
                source="optional_local_ocr",
                tokens=tokens,
            )
        )
    return DocumentTextLayer(pages=tuple(augmented))


def resolve_provenance(
    extraction: DocumentExtraction,
    text_layer: DocumentTextLayer,
    *,
    pages: Sequence[NormalizedPage] = (),
    ocr_provider: EvidenceOcrProvider | None = None,
    min_partial_characters: int = MIN_PARTIAL_CHARACTERS,
    min_partial_ratio: float = MIN_PARTIAL_RATIO,
) -> ProvenanceCollection:
    """Resolve every located field of one extraction against the local document."""

    effective_layer = text_layer
    if ocr_provider is not None and pages:
        effective_layer = _ocr_augmented_layer(text_layer, pages, ocr_provider)

    index = build_match_index(effective_layer)
    page_count = len(effective_layer.pages) or None
    fields = [
        resolve_field_provenance(
            field_path,
            located,
            index,
            page_count=page_count,
            min_partial_characters=min_partial_characters,
            min_partial_ratio=min_partial_ratio,
        )
        for field_path, located in iter_located_fields(extraction)
    ]

    counts = {
        status: sum(field.verification_status == status for field in fields)
        for status in ("verified", "approximate", "ambiguous", "page_only", "unresolved")
    }
    return ProvenanceCollection(
        text_layer_pages=sum(
            1 for page in effective_layer.pages if page.source == "native_pdf_text"
        ),
        ocr_pages=sum(
            1 for page in effective_layer.pages if page.source == "optional_local_ocr"
        ),
        fields=fields,
        summary=ProvenanceSummary(field_count=len(fields), **counts),
    )
