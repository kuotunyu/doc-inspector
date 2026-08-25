import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_portfolio_brief_preserves_evidence_and_product_boundaries() -> None:
    brief_path = ROOT / "docs" / "PORTFOLIO_BRIEF.md"
    case_study_path = ROOT / "docs" / "CASE_STUDY.md"
    readme_path = ROOT / "README.md"
    xfund_artifact_path = ROOT / "docs" / "assets" / "xfund-extraction-benchmark.json"
    assert brief_path.is_file(), "缺少 portfolio brief"
    assert case_study_path.is_file(), "缺少 case study"
    assert readme_path.is_file(), "缺少 README"
    assert xfund_artifact_path.is_file(), "缺少 XFUND artifact"

    text = brief_path.read_text(encoding="utf-8")
    case_study_text = case_study_path.read_text(encoding="utf-8")
    readme_text = readme_path.read_text(encoding="utf-8")
    xfund_artifact = json.loads(xfund_artifact_path.read_text(encoding="utf-8"))
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
    recruiter_link = (
        "[**Portfolio Brief（recruiter path）**](docs/PORTFOLIO_BRIEF.md)"
    )
    case_study_markers = (
        "低於 production-grade extraction",
        "不能視為真實案件可用性或可部署就緒證據",
    )
    deployment_markers = (
        "fixed runtime-critical allowlist",
        "19 non-README files byte-for-byte",
        "README metadata/body",
        "Git archive hygiene separately excludes private/planning paths",
    )

    for marker in (*required_sections, *required_markers):
        assert marker in text, f"portfolio brief 缺少必要標記：{marker}"
    assert recruiter_link in readme_text, "README 缺少 recruiter portfolio brief 連結"
    expected_xfund_values = tuple(
        f"{result['metrics']['micro_f1']:.4f}" for result in xfund_artifact["results"]
    )
    for value in expected_xfund_values:
        assert value in case_study_text, f"case study 缺少 XFUND micro F1：{value}"
    for marker in case_study_markers:
        assert marker in case_study_text, f"case study 缺少必要限制：{marker}"
    for marker in deployment_markers:
        assert marker in text, f"portfolio brief 缺少部署契約標記：{marker}"
    assert "compare the allowed public files" not in text, (
        "portfolio brief 不應使用涵蓋過廣的部署驗證敘述"
    )
