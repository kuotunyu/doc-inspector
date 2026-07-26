from __future__ import annotations

from pathlib import Path

from doc_inspector.docs_verify import public_markdown_files, verify_public_docs


def test_public_documentation_links_are_valid() -> None:
    root = Path(__file__).resolve().parents[1]
    report = verify_public_docs(root)
    public_paths = {
        path.relative_to(root).as_posix() for path in public_markdown_files(root)
    }

    assert report["ready"] is True
    assert report["file_count"] == len(public_paths)
    assert {
        "README.md",
        "CHANGELOG.md",
        ".github/CONTRIBUTING.md",
        ".github/SECURITY.md",
        "docs/CASE_STUDY.md",
        "docs/DECISION_EVALUATION.md",
        "docs/REMOTE_SETUP.md",
    } <= public_paths
    assert report["missing_links"] == []
    assert report["outside_workspace_links"] == []
    assert report["private_path_markers"] == []
    assert report["uses_network"] is False
    assert report["reads_env_truth"] is False


def test_public_documentation_reports_broken_and_private_links(
    tmp_path: Path,
) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / ".github").mkdir()
    (tmp_path / "README.md").write_text(
        "[missing](docs/missing.md)\n[outside](../private.md)\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "guide.md").write_text(
        "private path: C:\\Users\\example\\secret\n",
        encoding="utf-8",
    )
    (tmp_path / ".github" / "pull_request_template.md").write_text(
        "[missing](../docs/missing-from-template.md)\n",
        encoding="utf-8",
    )

    report = verify_public_docs(tmp_path)

    assert report["ready"] is False
    assert report["missing_links"] == [
        {
            "source": ".github/pull_request_template.md",
            "target": "../docs/missing-from-template.md",
        },
        {"source": "README.md", "target": "docs/missing.md"},
    ]
    assert report["outside_workspace_links"] == [
        {"source": "README.md", "target": "../private.md"}
    ]
    assert report["private_path_markers"] == [
        {"source": "docs/guide.md", "marker": "C:\\Users\\"}
    ]
