import json
from pathlib import Path
import subprocess
import sys

from scripts_support import load_script_module


verify_release = load_script_module("verify_release")


def test_public_release_bundle_is_ready_for_manual_handoff() -> None:
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, str(root / "scripts" / "verify_release.py")],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    report = json.loads(completed.stdout)

    assert completed.returncode == 0
    assert report["ready_for_manual_handoff"] is True
    assert report["required_file_count"] == 37
    assert report["missing_files"] == []
    assert report["unexpected_public_files"] == []
    assert report["expected_release_version"] == "1.1.2"
    assert report["project_version"] == "1.1.2"
    assert report["locked_project_versions"] == ["1.1.2"]
    assert report["release_version_issues"] == []
    assert report["project_author"] == "kuotunyu"
    assert report["project_author_issues"] == []
    assert report["missing_readme_markers"] == []
    assert report["public_readme_issues"] == []
    assert report["missing_ci_workflow_markers"] == []
    assert report["forbidden_ci_workflow_markers"] == []
    assert report["missing_dependabot_markers"] == []
    assert report["missing_codeowners_markers"] == []
    assert report["codeowners_rules"] == ["* @kuotunyu"]
    assert report["codeowners_issues"] == []
    assert report["decision_evaluation_issues"] == []
    assert report["provenance_evaluation_issues"] == []
    assert report["missing_remote_setup_markers"] == []
    assert report["forbidden_remote_setup_markers"] == []
    assert report["missing_public_safety_markers"] == []
    assert report["private_path_markers"] == []
    assert report["missing_secret_placeholders"] == []
    assert report["non_empty_secret_placeholders"] == []
    assert report["missing_gitignore_rules"] == []
    assert report["missing_dockerignore_rules"] == []
    assert report["reads_env_truth"] is False
    assert report["performs_network_calls"] is False


def test_release_guide_rejects_a_hardcoded_version_tag_command() -> None:
    guide = "git tag -a v1.2.3 -m 'release'\ngit push origin v1.2.3\n"

    issues = verify_release._hardcoded_release_version_markers(guide)

    assert issues == [
        "git push origin v1.2.3",
        "git tag -a v1.2.3",
    ]


def test_release_guide_rejects_version_specific_test_evidence() -> None:
    guide = """\
- 完整 extras：150 項測試，總 coverage 89%。
- GitHub 基礎路徑：147 passed、1 skipped，coverage 87%。
"""

    issues = verify_release._version_specific_test_evidence_markers(guide)

    assert issues == [
        "GitHub 基礎路徑：147 passed、1 skipped，coverage 87%。",
        "完整 extras：150 項測試，總 coverage 89%。",
    ]


def test_public_readme_rejects_space_frontmatter() -> None:
    public_readme = """\
---
sdk: docker
app_port: 7861
---

# Doc Inspector
"""

    issues = verify_release._public_readme_space_metadata_issues(public_readme)

    assert issues == ["README.md:space-frontmatter"]
    assert verify_release._public_readme_space_metadata_issues(
        "# Doc Inspector\n"
    ) == []
