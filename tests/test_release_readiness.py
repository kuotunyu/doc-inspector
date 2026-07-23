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
    assert report["missing_readme_markers"] == []
    assert report["missing_remote_setup_markers"] == []
    assert report["missing_public_safety_markers"] == []
    assert report["private_path_markers"] == []
    assert report["missing_secret_placeholders"] == []
    assert report["non_empty_secret_placeholders"] == []
    assert report["missing_gitignore_rules"] == []
    assert report["missing_dockerignore_rules"] == []
    assert report["reads_env_truth"] is False
    assert report["performs_network_calls"] is False
