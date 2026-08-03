"""Secret-safe static verification for the public release handoff."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_RELEASE_VERSION = "1.1.0"
EXPECTED_PROJECT_AUTHOR = "kuotunyu"
EXPECTED_CODEOWNERS_RULES = ("* @kuotunyu",)

REQUIRED_FILES = (
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    ".github/CONTRIBUTING.md",
    ".github/SECURITY.md",
    "Dockerfile",
    ".dockerignore",
    ".env.example",
    ".github/workflows/ci.yml",
    ".github/CODEOWNERS",
    ".github/dependabot.yml",
    ".github/pull_request_template.md",
    "pyproject.toml",
    "uv.lock",
    "data/evaluation/decision_cases.json",
    "data/evaluation/provenance/manifest.json",
    "docs/CASE_STUDY.md",
    "docs/DECISION_EVALUATION.md",
    "docs/EVIDENCE_PROVENANCE.md",
    "docs/REMOTE_SETUP.md",
    "docs/assets/desktop.png",
    "docs/assets/evidence-provenance.png",
    "docs/assets/decision-evaluation.json",
    "docs/assets/provenance-evaluation.json",
    "docs/assets/xfund-extraction-benchmark.json",
    "docs/assets/colqwen-retrieval-benchmark.json",
    "scripts/audit_ui_quality.py",
    "scripts/build_provenance_corpus.py",
    "scripts/run_provenance_evaluation.py",
    "scripts/check_github_ci.py",
    "scripts/check_github_contributors.py",
    "scripts/check_live_space.py",
    "scripts/check_space_snapshot.py",
    "scripts/serve_ui_fixture.py",
    "scripts/verify_distribution.py",
    "scripts/verify_public_docs.py",
    "scripts/verify_ui_layout.py",
)

UNNECESSARY_PUBLIC_FILES = (
    "PRODUCT.md",
    "DEPLOYMENT.md",
    "docs/UI_AUDIT.md",
    "docs/RELEASE_NOTES_v1.0.0.md",
    "docs/assets/browser-report.json",
    "docs/assets/ui-quality-audit.json",
    "docs/assets/wide.png",
    "docs/assets/mobile.png",
    "docs/assets/result-red.png",
)

REMOTE_SETUP_MARKERS = (
    "GitHub 主倉 → Hugging Face 部署鏡像",
    "https://github.com/kuotunyu/doc-inspector",
    "https://huggingface.co/spaces/steven0226/doc-inspector",
    "git -c core.autocrlf=false archive",
    "git hash-object --no-filters",
    "uvx --from huggingface_hub hf upload",
    "--delete '*'",
    "不要再對 Space 使用 force push",
    "PUBLIC_MAX_REQUESTS_PER_HOUR=60",
    "scripts/check_live_space.py",
    "私人驗收清單",
    "回復方式",
    "Set-Location '<專案資料夾>'",
    "git config user.email",
    "Co-authored-by",
    "不要直接 merge、squash 或 rebase",
    "scripts/check_github_ci.py",
    "scripts/check_github_contributors.py",
    "scripts/check_space_snapshot.py",
    "line_ending_only_mismatches",
    "https://github.com/kuotunyu/doc-inspector/graphs/contributors",
)

REMOTE_SETUP_FORBIDDEN_MARKERS = (
    "git push hf",
    "git push --force-with-lease hf",
    "git archive --format=zip",
)

README_MARKERS = (
    "sdk: docker",
    "app_port: 7861",
    "license: mit",
    "我常看到補助申請真正困難的地方",
    "## 架構",
    "```mermaid",
    "## 模型選型與台灣生態系對照",
    "## 快速開始",
    "## XFUND 評估",
    "## 成本",
    "## 隱私與安全邊界",
    "## Demo 資料與授權",
    "## CPU 容器與部署",
    "## 目前限制",
    "v1.1.0",
    "Hugging Face Docker Space",
    "254 passed，總 coverage 91%",
    "https://steven0226-doc-inspector.hf.space",
    "[![CI]",
    "## 專案導覽",
    "## 可驗證成果",
    "## 決策層產品評估",
    "## 來源核驗",
    "docs/CASE_STUDY.md",
    "docs/DECISION_EVALUATION.md",
    "docs/EVIDENCE_PROVENANCE.md",
    "24 / 24",
    "false verified rate",
)

CI_WORKFLOW_MARKERS = (
    "contents: read",
    "ubuntu-latest",
    "windows-latest",
    "python-version: \"3.11\"",
    "uv lock --check",
    "uv sync --locked --all-groups",
    "--cov-fail-under=85",
    "python scripts/verify_deployment.py",
    "python -m compileall -q src scripts tests",
    "python scripts/run_product_evaluation.py --check",
    "python scripts/run_provenance_evaluation.py --check",
    "python scripts/verify_public_docs.py",
    "uv build --clear --no-build-isolation",
    "python scripts/verify_distribution.py",
    "python scripts/verify_release.py",
)

CI_WORKFLOW_FORBIDDEN_MARKERS = (
    "pull_request_target",
    "secrets.",
)

DEPENDABOT_MARKERS = (
    'package-ecosystem: "uv"',
    'package-ecosystem: "github-actions"',
    'package-ecosystem: "docker"',
)

CODEOWNERS_MARKERS = (
    "* @kuotunyu",
)

SECRET_PLACEHOLDERS = (
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "HF_TOKEN",
    "DISCORD_WEBHOOK_URL",
)


def _parse_env_example(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def build_release_report(root: Path = ROOT) -> dict[str, object]:
    missing_files = [path for path in REQUIRED_FILES if not (root / path).is_file()]
    unexpected_public_files = [
        path for path in UNNECESSARY_PUBLIC_FILES if (root / path).is_file()
    ]

    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    lockfile = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    project_version = pyproject.get("project", {}).get("version")
    project_authors = pyproject.get("project", {}).get("authors", [])
    project_author = (
        project_authors[0].get("name")
        if len(project_authors) == 1 and isinstance(project_authors[0], dict)
        else None
    )
    locked_project_versions = [
        package.get("version")
        for package in lockfile.get("package", [])
        if package.get("name") == "doc-inspector"
    ]
    release_version_issues: list[str] = []
    if project_version != EXPECTED_RELEASE_VERSION:
        release_version_issues.append("pyproject.toml")
    if locked_project_versions != [EXPECTED_RELEASE_VERSION]:
        release_version_issues.append("uv.lock")
    project_author_issues = []
    if project_author != EXPECTED_PROJECT_AUTHOR:
        project_author_issues.append("pyproject.toml")

    readme = (root / "README.md").read_text(encoding="utf-8")
    missing_readme_markers = [
        marker for marker in README_MARKERS if marker not in readme
    ]
    ci_workflow = (root / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    missing_ci_workflow_markers = [
        marker for marker in CI_WORKFLOW_MARKERS if marker not in ci_workflow
    ]
    forbidden_ci_workflow_markers = [
        marker for marker in CI_WORKFLOW_FORBIDDEN_MARKERS if marker in ci_workflow
    ]
    dependabot = (root / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    missing_dependabot_markers = [
        marker for marker in DEPENDABOT_MARKERS if marker not in dependabot
    ]
    codeowners = (root / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    missing_codeowners_markers = [
        marker for marker in CODEOWNERS_MARKERS if marker not in codeowners
    ]
    codeowners_rules = tuple(
        line.strip()
        for line in codeowners.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    codeowners_issues = []
    if codeowners_rules != EXPECTED_CODEOWNERS_RULES:
        codeowners_issues.append(".github/CODEOWNERS")
    decision_evaluation = json.loads(
        (root / "docs" / "assets" / "decision-evaluation.json").read_text(
            encoding="utf-8"
        )
    )
    decision_cases = json.loads(
        (root / "data" / "evaluation" / "decision_cases.json").read_text(
            encoding="utf-8"
        )
    )
    decision_evaluation_issues: list[str] = []
    if decision_evaluation.get("passed") is not True:
        decision_evaluation_issues.append("passed")
    if decision_evaluation.get("uses_network") is not False:
        decision_evaluation_issues.append("uses_network")
    if decision_evaluation.get("uses_api_keys") is not False:
        decision_evaluation_issues.append("uses_api_keys")
    if "人工" not in decision_evaluation.get("oracle_method", ""):
        decision_evaluation_issues.append("oracle_method")
    if decision_evaluation.get("oracle_method") != decision_cases.get("oracle_method"):
        decision_evaluation_issues.append("oracle_method.drift")
    if decision_evaluation.get("benchmark_version") != decision_cases.get("version"):
        decision_evaluation_issues.append("benchmark_version")
    metrics = decision_evaluation.get("metrics", {})
    expected_case_count = len(decision_cases.get("cases", []))
    if metrics.get("case_count") != expected_case_count or expected_case_count < 20:
        decision_evaluation_issues.append("metrics.case_count")
    for metric_name in (
        "exact_case_match_rate",
        "overall_status_accuracy",
        "issue_precision",
        "issue_recall",
        "red_issue_recall",
        "yellow_issue_recall",
    ):
        if metrics.get(metric_name) != 1.0:
            decision_evaluation_issues.append(f"metrics.{metric_name}")
    if any(case.get("passed") is not True for case in decision_evaluation.get("cases", [])):
        decision_evaluation_issues.append("cases.passed")

    provenance_evaluation = json.loads(
        (root / "docs" / "assets" / "provenance-evaluation.json").read_text(
            encoding="utf-8"
        )
    )
    provenance_corpus = json.loads(
        (root / "data" / "evaluation" / "provenance" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    provenance_issues: list[str] = []
    if provenance_evaluation.get("passed") is not True:
        provenance_issues.append("provenance.passed")
    if provenance_evaluation.get("gate_failures"):
        provenance_issues.append("provenance.gate_failures")
    if provenance_evaluation.get("corpus_checksums_verified") is not True:
        provenance_issues.append("provenance.corpus_checksums_verified")
    for flag in ("uses_network", "uses_api_keys", "uses_gpu"):
        if provenance_evaluation.get(flag) is not False:
            provenance_issues.append(f"provenance.{flag}")
    if provenance_evaluation.get("corpus_version") != provenance_corpus.get("version"):
        provenance_issues.append("provenance.corpus_version")
    if provenance_corpus.get("contains_real_personal_data") is not False:
        provenance_issues.append("provenance.contains_real_personal_data")
    if provenance_corpus.get("localizable_field_count", 0) < 40:
        provenance_issues.append("provenance.localizable_field_count")
    provenance_metrics = provenance_evaluation.get("metrics", {})
    if provenance_metrics.get("false_verified_rate") != 0.0:
        provenance_issues.append("provenance.false_verified_rate")
    if provenance_metrics.get("page_localization_accuracy", 0.0) < 0.95:
        provenance_issues.append("provenance.page_localization_accuracy")
    if provenance_metrics.get("verified_bbox_hit_rate", 0.0) < 0.90:
        provenance_issues.append("provenance.verified_bbox_hit_rate")
    if any(
        outcome.get("false_verified") is True
        for outcome in provenance_evaluation.get("outcomes", [])
    ):
        provenance_issues.append("provenance.outcomes.false_verified")
    if not (root / "data" / "evaluation" / "provenance").glob("*.pdf"):
        provenance_issues.append("provenance.corpus_documents")
    for entry in provenance_corpus.get("documents", []):
        document_path = root / "data" / "evaluation" / "provenance" / str(entry.get("file"))
        if not document_path.is_file():
            provenance_issues.append(f"provenance.missing:{entry.get('file')}")
    remote_setup = (root / "docs" / "REMOTE_SETUP.md").read_text(encoding="utf-8")
    missing_remote_setup_markers = [
        marker for marker in REMOTE_SETUP_MARKERS if marker not in remote_setup
    ]
    forbidden_remote_setup_markers = [
        marker for marker in REMOTE_SETUP_FORBIDDEN_MARKERS if marker in remote_setup
    ]
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    missing_public_safety_markers = [
        marker
        for marker in (
            "PUBLIC_MAX_REQUESTS_PER_HOUR=60",
            "USER appuser",
        )
        if marker not in dockerfile
    ]

    env_values = _parse_env_example(
        (root / ".env.example").read_text(encoding="utf-8")
    )
    missing_secret_placeholders = [
        key for key in SECRET_PLACEHOLDERS if key not in env_values
    ]
    non_empty_secret_placeholders = [
        key for key in SECRET_PLACEHOLDERS if env_values.get(key)
    ]

    public_handoff_text = "\n".join(
        (
            readme,
            remote_setup,
        )
    )
    private_path_markers = [
        marker for marker in ("C:\\Users\\", "/Users/", "/home/") if marker in public_handoff_text
    ]

    gitignore = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    dockerignore = (root / ".dockerignore").read_text(encoding="utf-8").splitlines()
    missing_gitignore_rules = [
        rule
        for rule in (
            ".env",
            ".env.*",
            ".agents/",
            "AGENTS.md",
            "CLAUDE.md",
            "PLAN.md",
            "PROGRESS.md",
            "data/raw/",
            "outputs/",
            "logs/",
        )
        if rule not in gitignore
    ]
    missing_dockerignore_rules = [
        rule
        for rule in (
            ".env",
            ".env.*",
            ".agents/",
            "AGENTS.md",
            "CLAUDE.md",
            "PLAN.md",
            "PROGRESS.md",
            "data/",
            "outputs/",
            "logs/",
        )
        if rule not in dockerignore
    ]

    issues = (
        missing_files
        + unexpected_public_files
        + release_version_issues
        + project_author_issues
        + missing_readme_markers
        + missing_ci_workflow_markers
        + forbidden_ci_workflow_markers
        + missing_dependabot_markers
        + missing_codeowners_markers
        + codeowners_issues
        + decision_evaluation_issues
        + provenance_issues
        + missing_remote_setup_markers
        + forbidden_remote_setup_markers
        + missing_public_safety_markers
        + private_path_markers
        + missing_secret_placeholders
        + non_empty_secret_placeholders
        + missing_gitignore_rules
        + missing_dockerignore_rules
    )
    return {
        "ready_for_manual_handoff": not issues,
        "required_file_count": len(REQUIRED_FILES),
        "missing_files": missing_files,
        "unexpected_public_files": unexpected_public_files,
        "expected_release_version": EXPECTED_RELEASE_VERSION,
        "project_version": project_version,
        "locked_project_versions": locked_project_versions,
        "release_version_issues": release_version_issues,
        "project_author": project_author,
        "project_author_issues": project_author_issues,
        "missing_readme_markers": missing_readme_markers,
        "missing_ci_workflow_markers": missing_ci_workflow_markers,
        "forbidden_ci_workflow_markers": forbidden_ci_workflow_markers,
        "missing_dependabot_markers": missing_dependabot_markers,
        "missing_codeowners_markers": missing_codeowners_markers,
        "codeowners_rules": codeowners_rules,
        "codeowners_issues": codeowners_issues,
        "decision_evaluation_issues": decision_evaluation_issues,
        "provenance_evaluation_issues": provenance_issues,
        "missing_remote_setup_markers": missing_remote_setup_markers,
        "forbidden_remote_setup_markers": forbidden_remote_setup_markers,
        "missing_public_safety_markers": missing_public_safety_markers,
        "private_path_markers": private_path_markers,
        "missing_secret_placeholders": missing_secret_placeholders,
        "non_empty_secret_placeholders": non_empty_secret_placeholders,
        "missing_gitignore_rules": missing_gitignore_rules,
        "missing_dockerignore_rules": missing_dockerignore_rules,
        "reads_env_truth": False,
        "performs_network_calls": False,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    report = build_release_report()
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ready_for_manual_handoff"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
