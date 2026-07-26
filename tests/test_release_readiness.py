import json
from pathlib import Path
import subprocess
import sys


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
    assert report["missing_files"] == []
    assert report["expected_release_version"] == "1.0.0"
    assert report["project_version"] == "1.0.0"
    assert report["locked_project_versions"] == ["1.0.0"]
    assert report["release_version_issues"] == []
    assert report["project_author"] == "kuotunyu"
    assert report["project_author_issues"] == []
    assert report["missing_readme_markers"] == []
    assert report["missing_ci_workflow_markers"] == []
    assert report["forbidden_ci_workflow_markers"] == []
    assert report["missing_dependabot_markers"] == []
    assert report["missing_codeowners_markers"] == []
    assert report["codeowners_rules"] == ["* @kuotunyu"]
    assert report["codeowners_issues"] == []
    assert report["decision_evaluation_issues"] == []
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
