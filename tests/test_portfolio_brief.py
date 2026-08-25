from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_portfolio_brief_preserves_evidence_and_product_boundaries() -> None:
    brief_path = ROOT / "docs" / "PORTFOLIO_BRIEF.md"
    assert brief_path.is_file(), "缺少 portfolio brief"

    text = brief_path.read_text(encoding="utf-8")
    required_sections = (
        "## Product",
        "## Architecture",
        "## Evidence",
        "## Deployment lineage",
        "## Boundaries",
    )
    required_markers = (
        "https://github.com/kuotunyu/doc-inspector",
        "https://huggingface.co/spaces/steven0226/doc-inspector",
        "0.4471",
        "0.4819",
        "24 / 24",
        "provider/privacy boundary",
        "below production-grade extraction",
    )

    for marker in (*required_sections, *required_markers):
        assert marker in text, f"portfolio brief 缺少必要標記：{marker}"
