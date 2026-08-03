from __future__ import annotations

from io import BytesIO
from pathlib import Path
import tarfile

from scripts_support import load_script_module


verify_distribution = load_script_module("verify_distribution")


VERSION = "1.1.0"
ARCHIVE_ROOT = f"doc_inspector-{VERSION}"
TRACKED_SOURCE_FILES = {
    "LICENSE",
    "README.md",
    "pyproject.toml",
    "src/doc_inspector/__init__.py",
}


def _write_sdist(path: Path, extra_files: set[str]) -> None:
    files = TRACKED_SOURCE_FILES | extra_files
    with tarfile.open(path, mode="w:gz") as archive:
        for relative_path in sorted(files):
            payload = b"test fixture\n"
            member = tarfile.TarInfo(f"{ARCHIVE_ROOT}/{relative_path}")
            member.size = len(payload)
            archive.addfile(member, BytesIO(payload))


def test_sdist_rejects_private_interview_file(tmp_path: Path) -> None:
    archive_path = tmp_path / f"{ARCHIVE_ROOT}.tar.gz"
    _write_sdist(archive_path, {"interview.md"})

    report = verify_distribution._verify_sdist(
        archive_path,
        VERSION,
        tracked_source_files=TRACKED_SOURCE_FILES,
    )

    assert f"{ARCHIVE_ROOT}/interview.md" in report["forbidden_entries"]
    assert report["untracked_entries"] == [f"{ARCHIVE_ROOT}/interview.md"]


def test_sdist_rejects_arbitrary_untracked_local_file(tmp_path: Path) -> None:
    archive_path = tmp_path / f"{ARCHIVE_ROOT}.tar.gz"
    _write_sdist(archive_path, {"local-review-notes.txt"})

    report = verify_distribution._verify_sdist(
        archive_path,
        VERSION,
        tracked_source_files=TRACKED_SOURCE_FILES,
    )

    assert report["untracked_entries"] == [
        f"{ARCHIVE_ROOT}/local-review-notes.txt"
    ]


def test_sdist_allows_generated_pkg_info_metadata(tmp_path: Path) -> None:
    archive_path = tmp_path / f"{ARCHIVE_ROOT}.tar.gz"
    _write_sdist(archive_path, {"PKG-INFO"})

    report = verify_distribution._verify_sdist(
        archive_path,
        VERSION,
        tracked_source_files=TRACKED_SOURCE_FILES,
    )

    assert report["untracked_entries"] == []
