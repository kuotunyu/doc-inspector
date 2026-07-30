"""Generate the fixed synthetic evidence-provenance corpus and its ground truth.

Ground truth is written by this generator from the authored page layout: the
text of every line, the insertion point, the font metrics, and the page rotation
are all known here before any PDF exists. Nothing in this file reads PyMuPDF's
text extraction or the provenance resolver, so the corpus can never be tuned to
match the system it is used to measure.

The documents contain no real personal data: every name, identifier, address,
and amount is invented and marked as synthetic on the page itself.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field as dataclass_field
from hashlib import sha256
import json
from pathlib import Path
import sys

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "evaluation" / "provenance"

CORPUS_NAME = "doc-inspector-evidence-provenance"
CORPUS_VERSION = "1.0.0"
CORPUS_SEED = 20260730
FONT_NAME = "china-t"
COORDINATE_SPACE = "normalized_1000_top_left"
COORDINATE_SCALE = 1000.0
WATERMARK = "合成測試資料／非真實文件"

BODY_SIZE = 13.0
LEFT_MARGIN = 64.0
FIRST_BASELINE = 96.0
LEADING = 30.0


@dataclass(frozen=True)
class PageSpec:
    """One authored page: its literal lines plus its geometry."""

    lines: tuple[str, ...]
    width: float = 595.0
    height: float = 842.0
    rotation: int = 0
    rasterize: bool = False
    scale: float = 1.0


@dataclass(frozen=True)
class Anchor:
    """Where a field's evidence physically sits, expressed in authored text."""

    page: int
    fragments: tuple[str, ...]


@dataclass(frozen=True)
class FieldSpec:
    """One provider claim plus the outcome the resolver is expected to reach."""

    field_path: str
    case_type: str
    expected_status: str
    value: str | None = None
    claimed_page: int | None = None
    evidence: str | None = None
    anchor: Anchor | None = None
    id_type: bool = False
    label: str | None = None


@dataclass(frozen=True)
class DocumentSpec:
    """One corpus document: its pages, its claims, and its expected outcomes."""

    name: str
    schema_name: str
    pages: tuple[PageSpec, ...]
    fields: tuple[FieldSpec, ...]
    note: str
    extras: dict[str, object] = dataclass_field(default_factory=dict)


def _lines(*rows: str) -> tuple[str, ...]:
    return (WATERMARK, *rows)


DOCUMENT_A = DocumentSpec(
    name="doc_a_subsidy_four_pages",
    schema_name="subsidy_application",
    note="四頁標準補助申請表，所有欄位都應可由本機文字層唯一定位。",
    pages=(
        PageSpec(
            lines=_lines(
                "補助申請書（合成第一頁）",
                "補助方案：安心生活居家支持試辦計畫",
                "申請日期：2026-05-18",
                "身分別：主要照顧者本人",
                "申請人姓名：測試申請人卡拉",
                "證件種類：國民身分證",
                "證件號碼：A123456789",
                "出生日期：1978-03-02",
            )
        ),
        PageSpec(
            lines=_lines(
                "補助申請書（合成第二頁）",
                "聯絡電話：0912-345-678",
                "電子郵件：kara.demo@example.invalid",
                "通訊地址：測試市示範區永續路 88 巷 12 號 5 樓",
                "撥款帳戶名稱：測試申請人卡拉本人帳戶",
                "受益人身分別：受照顧家屬",
                "受益人姓名：測試受益人歐文",
                "受益人證件種類：居留證",
                "受益人證件號碼：FC12345678",
                "受益人出生日期：1946-11-27",
            )
        ),
        PageSpec(
            lines=_lines(
                "補助申請書（合成第三頁）：補助明細",
                "明細一項目：居家喘息服務費",
                "明細一金額：18,400",
                "明細二項目：無障礙浴室扶手安裝",
                "明細二金額：7,250",
                "明細三項目：長期照顧交通接送",
                "明細三金額：3,600",
            )
        ),
        PageSpec(
            lines=_lines(
                "補助申請書（合成第四頁）：金額彙總",
                "申請補助金額合計：29,250",
                "申報總額欄位：29,250 元整",
                "本頁僅供合成測試使用，不具行政效力。",
            )
        ),
    ),
    fields=(
        FieldSpec(
            "program_name",
            "normal",
            "verified",
            value="安心生活居家支持試辦計畫",
            claimed_page=1,
            evidence="補助方案：安心生活居家支持試辦計畫",
            anchor=Anchor(1, ("補助方案：安心生活居家支持試辦計畫",)),
        ),
        FieldSpec(
            "application_date",
            "normal",
            "verified",
            value="2026-05-18",
            claimed_page=1,
            evidence="申請日期：2026-05-18",
            anchor=Anchor(1, ("申請日期：2026-05-18",)),
        ),
        FieldSpec(
            "applicants.0.role",
            "normal",
            "verified",
            value="主要照顧者",
            claimed_page=1,
            evidence="身分別：主要照顧者本人",
            anchor=Anchor(1, ("身分別：主要照顧者本人",)),
        ),
        FieldSpec(
            "applicants.0.name",
            "normal",
            "verified",
            value="測試申請人卡拉",
            claimed_page=1,
            evidence="申請人姓名：測試申請人卡拉",
            anchor=Anchor(1, ("申請人姓名：測試申請人卡拉",)),
        ),
        FieldSpec(
            "applicants.0.id_type",
            "normal",
            "verified",
            value="citizen_id",
            claimed_page=1,
            evidence="證件種類：國民身分證",
            anchor=Anchor(1, ("證件種類：國民身分證",)),
            id_type=True,
        ),
        FieldSpec(
            "applicants.0.id_number",
            "normal",
            "verified",
            value="A123456789",
            claimed_page=1,
            evidence="證件號碼：A123456789",
            anchor=Anchor(1, ("證件號碼：A123456789",)),
        ),
        FieldSpec(
            "applicants.0.birth_date",
            "normal",
            "verified",
            value="1978-03-02",
            claimed_page=1,
            evidence="出生日期：1978-03-02",
            anchor=Anchor(1, ("出生日期：1978-03-02",)),
        ),
        FieldSpec(
            "contact_phone",
            "normal",
            "verified",
            value="0912-345-678",
            claimed_page=2,
            evidence="聯絡電話：0912-345-678",
            anchor=Anchor(2, ("聯絡電話：0912-345-678",)),
        ),
        FieldSpec(
            "contact_email",
            "normal",
            "verified",
            value="kara.demo@example.invalid",
            claimed_page=2,
            evidence="電子郵件：kara.demo@example.invalid",
            anchor=Anchor(2, ("電子郵件：kara.demo@example.invalid",)),
        ),
        FieldSpec(
            "address",
            "normal",
            "verified",
            value="測試市示範區永續路 88 巷 12 號 5 樓",
            claimed_page=2,
            evidence="通訊地址：測試市示範區永續路 88 巷 12 號 5 樓",
            anchor=Anchor(2, ("通訊地址：測試市示範區永續路 88 巷 12 號 5 樓",)),
        ),
        FieldSpec(
            "bank_account_display_name",
            "normal",
            "verified",
            value="測試申請人卡拉本人帳戶",
            claimed_page=2,
            evidence="撥款帳戶名稱：測試申請人卡拉本人帳戶",
            anchor=Anchor(2, ("撥款帳戶名稱：測試申請人卡拉本人帳戶",)),
        ),
        FieldSpec(
            "beneficiaries.0.role",
            "normal",
            "verified",
            value="受照顧家屬",
            claimed_page=2,
            evidence="受益人身分別：受照顧家屬",
            anchor=Anchor(2, ("受益人身分別：受照顧家屬",)),
        ),
        FieldSpec(
            "beneficiaries.0.name",
            "normal",
            "verified",
            value="測試受益人歐文",
            claimed_page=2,
            evidence="受益人姓名：測試受益人歐文",
            anchor=Anchor(2, ("受益人姓名：測試受益人歐文",)),
        ),
        FieldSpec(
            "beneficiaries.0.id_type",
            "normal",
            "verified",
            value="resident_id",
            claimed_page=2,
            evidence="受益人證件種類：居留證",
            anchor=Anchor(2, ("受益人證件種類：居留證",)),
            id_type=True,
        ),
        FieldSpec(
            "beneficiaries.0.id_number",
            "normal",
            "verified",
            value="FC12345678",
            claimed_page=2,
            evidence="受益人證件號碼：FC12345678",
            anchor=Anchor(2, ("受益人證件號碼：FC12345678",)),
        ),
        FieldSpec(
            "beneficiaries.0.birth_date",
            "normal",
            "verified",
            value="1946-11-27",
            claimed_page=2,
            evidence="受益人出生日期：1946-11-27",
            anchor=Anchor(2, ("受益人出生日期：1946-11-27",)),
        ),
        FieldSpec(
            "line_items.0.description",
            "nested_list",
            "verified",
            value="居家喘息服務費",
            claimed_page=3,
            evidence="明細一項目：居家喘息服務費",
            anchor=Anchor(3, ("明細一項目：居家喘息服務費",)),
        ),
        FieldSpec(
            "line_items.0.amount",
            "nested_list",
            "verified",
            value="18400",
            claimed_page=3,
            evidence="明細一金額：18,400",
            anchor=Anchor(3, ("明細一金額：18,400",)),
        ),
        FieldSpec(
            "line_items.1.description",
            "nested_list",
            "verified",
            value="無障礙浴室扶手安裝",
            claimed_page=3,
            evidence="明細二項目：無障礙浴室扶手安裝",
            anchor=Anchor(3, ("明細二項目：無障礙浴室扶手安裝",)),
        ),
        FieldSpec(
            "line_items.1.amount",
            "nested_list",
            "verified",
            value="7250",
            claimed_page=3,
            evidence="明細二金額：7,250",
            anchor=Anchor(3, ("明細二金額：7,250",)),
        ),
        FieldSpec(
            "line_items.2.description",
            "nested_list",
            "verified",
            value="長期照顧交通接送",
            claimed_page=3,
            evidence="明細三項目：長期照顧交通接送",
            anchor=Anchor(3, ("明細三項目：長期照顧交通接送",)),
        ),
        FieldSpec(
            "line_items.2.amount",
            "nested_list",
            "verified",
            value="3600",
            claimed_page=3,
            evidence="明細三金額：3,600",
            anchor=Anchor(3, ("明細三金額：3,600",)),
        ),
        FieldSpec(
            "requested_amount",
            "normal",
            "verified",
            value="29250",
            claimed_page=4,
            evidence="申請補助金額合計：29,250",
            anchor=Anchor(4, ("申請補助金額合計：29,250",)),
        ),
        FieldSpec(
            "declared_total",
            "normal",
            "verified",
            value="29250",
            claimed_page=4,
            evidence="申報總額欄位：29,250 元整",
            anchor=Anchor(4, ("申報總額欄位：29,250 元整",)),
        ),
        FieldSpec(
            "additional_fields.0.located_value",
            "separator_drift",
            "approximate",
            value="29250",
            claimed_page=4,
            evidence="申請補助金額合計：29250",
            anchor=Anchor(4, ("申請補助金額合計：29",)),
            label="金額（模型省略千分位）",
        ),
        FieldSpec(
            "additional_fields.1.located_value",
            "paraphrased_evidence",
            "unresolved",
            value="測試申請人卡拉",
            claimed_page=1,
            evidence="測試申請人卡拉（欄位：申請人姓名）",
            label="姓名（模型改寫語序）",
        ),
        FieldSpec(
            "additional_fields.2.located_value",
            "cross_page_evidence",
            "unresolved",
            value="29250",
            claimed_page=4,
            evidence="申請補助金額合計：29,250　補助方案：安心生活居家支持試辦計畫",
            label="跨頁拼接的證據",
        ),
    ),
)


DOCUMENT_B = DocumentSpec(
    name="doc_b_subsidy_rotated_and_oversized",
    schema_name="subsidy_application",
    note="第二頁旋轉 90 度、第三頁尺寸大到會觸發 render 後縮放；另含換行接合案例。",
    pages=(
        PageSpec(
            lines=_lines(
                "居家改善補助申請（合成，含旋轉頁）",
                "補助方案：無障礙住宅改善補助",
                "申請日期：2026-06-09",
                "申請人姓名：測試申請人黎明",
                "證件號碼：B234567891",
            )
        ),
        PageSpec(
            rotation=90,
            lines=_lines(
                "旋轉頁：聯絡與帳戶資料",
                "聯絡電話：0928-111-222",
                "通訊地址：測試縣旋轉鎮驗證路 7 號",
                "撥款帳戶名稱：測試申請人黎",
                "明無障礙改善專戶",
                "明細一項目：浴室防滑地磚",
                "明細一金額：12,900",
            ),
        ),
        PageSpec(
            width=1224.0,
            height=1584.0,
            scale=1.7,
            lines=_lines(
                "放大頁：金額彙總（合成）",
                "申請補助金額合計：12,900",
                "申報總額欄位：12,900 元整",
                "電子郵件：liming.demo@example.invalid",
            ),
        ),
    ),
    fields=(
        FieldSpec(
            "program_name",
            "normal",
            "verified",
            value="無障礙住宅改善補助",
            claimed_page=1,
            evidence="補助方案：無障礙住宅改善補助",
            anchor=Anchor(1, ("補助方案：無障礙住宅改善補助",)),
        ),
        FieldSpec(
            "application_date",
            "normal",
            "verified",
            value="2026-06-09",
            claimed_page=1,
            evidence="申請日期：2026-06-09",
            anchor=Anchor(1, ("申請日期：2026-06-09",)),
        ),
        FieldSpec(
            "applicants.0.name",
            "normal",
            "verified",
            value="測試申請人黎明",
            claimed_page=1,
            evidence="申請人姓名：測試申請人黎明",
            anchor=Anchor(1, ("申請人姓名：測試申請人黎明",)),
        ),
        FieldSpec(
            "applicants.0.id_number",
            "normal",
            "verified",
            value="B234567891",
            claimed_page=1,
            evidence="證件號碼：B234567891",
            anchor=Anchor(1, ("證件號碼：B234567891",)),
        ),
        FieldSpec(
            "contact_phone",
            "rotated_page",
            "verified",
            value="0928-111-222",
            claimed_page=2,
            evidence="聯絡電話：0928-111-222",
            anchor=Anchor(2, ("聯絡電話：0928-111-222",)),
        ),
        FieldSpec(
            "address",
            "rotated_page",
            "verified",
            value="測試縣旋轉鎮驗證路 7 號",
            claimed_page=2,
            evidence="通訊地址：測試縣旋轉鎮驗證路 7 號",
            anchor=Anchor(2, ("通訊地址：測試縣旋轉鎮驗證路 7 號",)),
        ),
        FieldSpec(
            "bank_account_display_name",
            "line_wrap_join",
            "verified",
            value="測試申請人黎明無障礙改善專戶",
            claimed_page=2,
            evidence="撥款帳戶名稱：測試申請人黎\n明無障礙改善專戶",
            anchor=Anchor(2, ("撥款帳戶名稱：測試申請人黎", "明無障礙改善專戶")),
        ),
        FieldSpec(
            "line_items.0.description",
            "rotated_page",
            "verified",
            value="浴室防滑地磚",
            claimed_page=2,
            evidence="明細一項目：浴室防滑地磚",
            anchor=Anchor(2, ("明細一項目：浴室防滑地磚",)),
        ),
        FieldSpec(
            "line_items.0.amount",
            "rotated_page",
            "verified",
            value="12900",
            claimed_page=2,
            evidence="明細一金額：12,900",
            anchor=Anchor(2, ("明細一金額：12,900",)),
        ),
        FieldSpec(
            "requested_amount",
            "render_resize",
            "verified",
            value="12900",
            claimed_page=3,
            evidence="申請補助金額合計：12,900",
            anchor=Anchor(3, ("申請補助金額合計：12,900",)),
        ),
        FieldSpec(
            "declared_total",
            "render_resize",
            "verified",
            value="12900",
            claimed_page=3,
            evidence="申報總額欄位：12,900 元整",
            anchor=Anchor(3, ("申報總額欄位：12,900 元整",)),
        ),
        FieldSpec(
            "contact_email",
            "render_resize",
            "verified",
            value="liming.demo@example.invalid",
            claimed_page=3,
            evidence="電子郵件：liming.demo@example.invalid",
            anchor=Anchor(3, ("電子郵件：liming.demo@example.invalid",)),
        ),
    ),
)


DOCUMENT_C = DocumentSpec(
    name="doc_c_receipt_failure_cases",
    schema_name="receipt",
    note="兩頁收據，集中放置重複值、錯誤頁碼、部分文字、空白雜訊與幻覺證據案例。",
    pages=(
        PageSpec(
            lines=_lines(
                "消費明細（合成第一頁）",
                "店家名稱：示範生活用品行",
                "單據號碼：SYN-2026-000731",
                "單據日期：2026-04-02",
                "幣別：TWD",
                "品項一：室內防滑拖鞋",
                "品項一數量：3",
                "品項一單價：260",
                "品項一金額：780",
                "重複列印標記：REPEATED-ON-ONE-PAGE",
                "重複列印標記：REPEATED-ON-ONE-PAGE",
                "跨頁標記：REPEATED-ACROSS-PAGES",
                "折扣金額：120",
            )
        ),
        PageSpec(
            lines=_lines(
                "消費明細（合成第二頁）",
                "品項小計：780",
                "營業稅額：39",
                "應付總額：699",
                "跨頁標記：REPEATED-ACROSS-PAGES",
                "備註欄位：本單據為合成測試資料，僅供系統驗證使用",
            )
        ),
    ),
    extras={
        "additional_field_labels": ["備註", "查核註記"],
    },
    fields=(
        FieldSpec(
            "merchant_name",
            "normal",
            "verified",
            value="示範生活用品行",
            claimed_page=1,
            evidence="店家名稱：示範生活用品行",
            anchor=Anchor(1, ("店家名稱：示範生活用品行",)),
        ),
        FieldSpec(
            "receipt_number",
            "normal",
            "verified",
            value="SYN-2026-000731",
            claimed_page=1,
            evidence="單據號碼：SYN-2026-000731",
            anchor=Anchor(1, ("單據號碼：SYN-2026-000731",)),
        ),
        FieldSpec(
            "receipt_date",
            "normal",
            "verified",
            value="2026-04-02",
            claimed_page=1,
            evidence="單據日期：2026-04-02",
            anchor=Anchor(1, ("單據日期：2026-04-02",)),
        ),
        FieldSpec(
            "currency",
            "partial_evidence",
            "verified",
            value="TWD",
            claimed_page=1,
            evidence="幣別：TWD",
            anchor=Anchor(1, ("幣別：TWD",)),
        ),
        FieldSpec(
            "line_items.0.description",
            "nested_list",
            "verified",
            value="室內防滑拖鞋",
            claimed_page=1,
            evidence="品項一：室內防滑拖鞋",
            anchor=Anchor(1, ("品項一：室內防滑拖鞋",)),
        ),
        FieldSpec(
            "line_items.0.quantity",
            "nested_list",
            "verified",
            value="3",
            claimed_page=1,
            evidence="品項一數量：3",
            anchor=Anchor(1, ("品項一數量：3",)),
        ),
        FieldSpec(
            "line_items.0.unit_price",
            "nested_list",
            "verified",
            value="260",
            claimed_page=1,
            evidence="品項一單價：260",
            anchor=Anchor(1, ("品項一單價：260",)),
        ),
        FieldSpec(
            "line_items.0.line_total",
            "nested_list",
            "verified",
            value="780",
            claimed_page=1,
            evidence="品項一金額：780",
            anchor=Anchor(1, ("品項一金額：780",)),
        ),
        FieldSpec(
            "line_items.1.description",
            "duplicate_same_page",
            "ambiguous",
            value="重複列印標記",
            claimed_page=1,
            evidence="重複列印標記：REPEATED-ON-ONE-PAGE",
        ),
        FieldSpec(
            "line_items.1.line_total",
            "duplicate_across_pages",
            "ambiguous",
            value="跨頁標記",
            claimed_page=1,
            evidence="跨頁標記：REPEATED-ACROSS-PAGES",
        ),
        FieldSpec(
            "line_items.2.description",
            "null_value",
            "unresolved",
            value=None,
            claimed_page=None,
            evidence=None,
        ),
        FieldSpec(
            "subtotal",
            "whitespace_noise",
            "verified",
            value="780",
            claimed_page=2,
            evidence="品項小計 ：  780",
            anchor=Anchor(2, ("品項小計：780",)),
        ),
        FieldSpec(
            "tax",
            "normal",
            "verified",
            value="39",
            claimed_page=2,
            evidence="營業稅額：39",
            anchor=Anchor(2, ("營業稅額：39",)),
        ),
        FieldSpec(
            "total",
            "normal",
            "verified",
            value="699",
            claimed_page=2,
            evidence="應付總額：699",
            anchor=Anchor(2, ("應付總額：699",)),
        ),
        FieldSpec(
            "discount",
            "wrong_claimed_page",
            "approximate",
            value="120",
            claimed_page=2,
            evidence="折扣金額：120",
            anchor=Anchor(1, ("折扣金額：120",)),
        ),
        FieldSpec(
            "fees",
            "hallucinated_evidence",
            "unresolved",
            value="45",
            claimed_page=2,
            evidence="服務費用：45（本行實際不存在於文件）",
        ),
        FieldSpec(
            "additional_fields.0.located_value",
            "partial_evidence",
            "verified",
            value="本單據為合成測試資料",
            claimed_page=2,
            evidence="本單據為合成測試資料",
            anchor=Anchor(2, ("本單據為合成測試資料",)),
            label="備註",
        ),
        FieldSpec(
            "additional_fields.1.located_value",
            "fuzzy_partial_match",
            "approximate",
            value="示範生活用品店",
            claimed_page=1,
            evidence="店家名稱：示範生活用品店",
            anchor=Anchor(1, ("店家名稱：示範生活用品",)),
            label="查核註記",
        ),
    ),
)


DOCUMENT_D = DocumentSpec(
    name="doc_d_receipt_scanned_image_only",
    schema_name="receipt",
    note="整份文件只有影像、沒有文字層，系統必須退化為 page_only 而不是猜位置。",
    pages=(
        PageSpec(
            rasterize=True,
            lines=_lines(
                "消費明細（合成掃描影像）",
                "店家名稱：掃描示範食材行",
                "單據日期：2026-01-15",
                "應付總額：452",
            ),
        ),
    ),
    fields=(
        FieldSpec(
            "merchant_name",
            "image_only_page",
            "page_only",
            value="掃描示範食材行",
            claimed_page=1,
            evidence="店家名稱：掃描示範食材行",
        ),
        FieldSpec(
            "receipt_date",
            "image_only_page",
            "page_only",
            value="2026-01-15",
            claimed_page=1,
            evidence="單據日期：2026-01-15",
        ),
        FieldSpec(
            "total",
            "image_only_page",
            "page_only",
            value="452",
            claimed_page=1,
            evidence="應付總額：452",
        ),
        FieldSpec(
            "subtotal",
            "claimed_page_out_of_range",
            "unresolved",
            value="452",
            claimed_page=4,
            evidence="小計金額：452",
        ),
    ),
)

SPEC: tuple[DocumentSpec, ...] = (DOCUMENT_A, DOCUMENT_B, DOCUMENT_C, DOCUMENT_D)


def _page_layout(page: PageSpec) -> tuple[tuple[str, float, float, float], ...]:
    """Return ``(text, size, x, baseline)`` for every authored line."""

    size = BODY_SIZE * page.scale
    leading = LEADING * page.scale
    left = LEFT_MARGIN * page.scale
    baseline = FIRST_BASELINE * page.scale
    layout: list[tuple[str, float, float, float]] = []
    for text in page.lines:
        layout.append((text, size, left, baseline))
        baseline += leading
    return tuple(layout)


def _normalized(
    rect: pymupdf.Rect,
    page_rect: pymupdf.Rect,
    rotation_matrix: pymupdf.Matrix,
) -> list[float]:
    rotated = rect * rotation_matrix
    x0 = (min(rotated.x0, rotated.x1) - page_rect.x0) / page_rect.width
    x1 = (max(rotated.x0, rotated.x1) - page_rect.x0) / page_rect.width
    y0 = (min(rotated.y0, rotated.y1) - page_rect.y0) / page_rect.height
    y1 = (max(rotated.y0, rotated.y1) - page_rect.y0) / page_rect.height
    return [
        round(max(0.0, min(1.0, value)) * COORDINATE_SCALE, 3)
        for value in (x0, y0, x1, y1)
    ]


def _fragment_rect(
    font: pymupdf.Font,
    layout: tuple[tuple[str, float, float, float], ...],
    fragment: str,
) -> pymupdf.Rect:
    """Locate one authored fragment and return its rectangle from font metrics."""

    matches = [
        (text, size, x, baseline, text.index(fragment))
        for text, size, x, baseline in layout
        if text.count(fragment) == 1
    ]
    if len(matches) != 1:
        raise ValueError(
            f"ground-truth fragment 必須在該頁剛好出現一次：{fragment!r}（找到 {len(matches)} 行）"
        )
    text, size, x, baseline, offset = matches[0]
    start = x + font.text_length(text[:offset], size)
    end = start + font.text_length(fragment, size)
    return pymupdf.Rect(
        start,
        baseline - font.ascender * size,
        end,
        baseline - font.descender * size,
    )


def _write_page(document: pymupdf.Document, spec: PageSpec, font: pymupdf.Font) -> None:
    target = document.new_page(width=spec.width, height=spec.height)
    writer = pymupdf.TextWriter(target.rect)
    for text, size, x, baseline in _page_layout(spec):
        writer.append((x, baseline), text, font=font, fontsize=size)
    if spec.rasterize:
        staging = pymupdf.open()
        try:
            staging_page = staging.new_page(width=spec.width, height=spec.height)
            staging_writer = pymupdf.TextWriter(staging_page.rect)
            for text, size, x, baseline in _page_layout(spec):
                staging_writer.append((x, baseline), text, font=font, fontsize=size)
            staging_writer.write_text(staging_page)
            pixmap = staging_page.get_pixmap(
                dpi=150, alpha=False, colorspace=pymupdf.csGRAY
            )
        finally:
            staging.close()
        target.insert_image(target.rect, stream=pixmap.tobytes("png"))
    else:
        writer.write_text(target)
    if spec.rotation:
        target.set_rotation(spec.rotation)


def _build_document(spec: DocumentSpec, destination: Path) -> dict[str, object]:
    font = pymupdf.Font(FONT_NAME)
    document = pymupdf.open()
    try:
        for page in spec.pages:
            _write_page(document, page, font)

        truths: dict[str, tuple[int | None, list[float] | None]] = {}
        for item in spec.fields:
            if item.anchor is None:
                truths[item.field_path] = (None, None)
                continue
            page_index = item.anchor.page - 1
            page = document[page_index]
            layout = _page_layout(spec.pages[page_index])
            rect: pymupdf.Rect | None = None
            for fragment in item.anchor.fragments:
                fragment_rect = _fragment_rect(font, layout, fragment)
                rect = fragment_rect if rect is None else rect | fragment_rect
            assert rect is not None
            truths[item.field_path] = (
                item.anchor.page,
                _normalized(rect, page.rect, page.rotation_matrix),
            )

        document.subset_fonts(verbose=False)
        document.set_metadata({})
        destination.parent.mkdir(parents=True, exist_ok=True)
        document.save(str(destination), garbage=4, deflate=True, no_new_id=True)
    finally:
        document.close()

    fields = []
    for item in spec.fields:
        truth_page, bbox = truths[item.field_path]
        fields.append(
            {
                "field_path": item.field_path,
                "case_type": item.case_type,
                "expected_status": item.expected_status,
                "localizable": item.expected_status in {"verified", "approximate"},
                "claim": {
                    "value": item.value,
                    "page_number": item.claimed_page,
                    "evidence_text": item.evidence,
                    "is_id_type": item.id_type,
                    "additional_field_label": item.label,
                },
                "truth_page": truth_page,
                "bbox": bbox,
            }
        )

    return {
        "name": spec.name,
        "file": destination.name,
        "sha256": sha256(destination.read_bytes()).hexdigest(),
        "byte_size": destination.stat().st_size,
        "schema_name": spec.schema_name,
        "page_count": len(spec.pages),
        "note": spec.note,
        "page_geometry": [
            {
                "page_number": index + 1,
                "width_points": page.width,
                "height_points": page.height,
                "rotation": page.rotation,
                "image_only": page.rasterize,
            }
            for index, page in enumerate(spec.pages)
        ],
        "fields": fields,
    }


def build_corpus(destination: Path = DEFAULT_OUTPUT) -> dict[str, object]:
    """Write every corpus PDF plus a manifest containing the ground truth."""

    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    documents = [
        _build_document(spec, destination / f"{spec.name}.pdf") for spec in SPEC
    ]
    manifest: dict[str, object] = {
        "corpus_name": CORPUS_NAME,
        "version": CORPUS_VERSION,
        "seed": CORPUS_SEED,
        "contains_real_personal_data": False,
        "coordinate_space": COORDINATE_SPACE,
        "coordinate_scale": COORDINATE_SCALE,
        "ground_truth_source": (
            "由文件生成器的版面規格與字型量測直接記錄，未讀取 PyMuPDF 文字抽取或 resolver 輸出。"
        ),
        "generator": {
            "script": "scripts/build_provenance_corpus.py",
            "library": "pymupdf",
            "library_version": pymupdf.VersionBind,
            "mupdf_version": pymupdf.VersionFitz,
            "font": FONT_NAME,
        },
        "documents": documents,
    }
    manifest["localizable_field_count"] = sum(
        1
        for document in documents
        for item in document["fields"]
        if item["localizable"]
    )
    manifest["field_count"] = sum(len(document["fields"]) for document in documents)
    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest = build_corpus(args.output)
    print(
        f"corpus：{manifest['field_count']} 欄位，"
        f"其中 {manifest['localizable_field_count']} 個具備 ground-truth 位置"
    )
    for document in manifest["documents"]:
        print(
            f"  {document['name']}｜{document['page_count']} 頁｜"
            f"{document['byte_size']:,} bytes｜{document['sha256'][:16]}…"
        )
    print(f"manifest：{args.output / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
