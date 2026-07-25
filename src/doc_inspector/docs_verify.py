"""Offline verification for public Markdown links and private path leakage."""

from __future__ import annotations

from pathlib import Path
import re
from urllib.parse import unquote


_MARKDOWN_LINK = re.compile(r"!?\[[^\]]*]\(([^)]+)\)")
_INTERNAL_ROOT_DOCS = {"CLAUDE.md", "PLAN.md", "PROGRESS.md"}
_PRIVATE_PATH_MARKERS = ("C:\\Users\\", "/Users/", "/home/")


def public_markdown_files(root: Path) -> list[Path]:
    """Return public Markdown without local workflow notes."""

    root = Path(root).resolve()
    files = [
        path
        for path in root.glob("*.md")
        if path.name not in _INTERNAL_ROOT_DOCS
    ]
    files.extend((root / "docs").rglob("*.md"))
    files.extend((root / ".github").rglob("*.md"))
    return sorted(path for path in files if path.is_file())


def _local_target(raw_target: str) -> str | None:
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    if not target or target.startswith(("#", "http://", "https://", "mailto:")):
        return None
    if " " in target:
        target = target.split(" ", maxsplit=1)[0]
    return unquote(target.split("#", maxsplit=1)[0])


def verify_public_docs(root: Path) -> dict[str, object]:
    """Check public documentation without network or Git metadata."""

    root = Path(root).resolve()
    missing_links: list[dict[str, str]] = []
    outside_workspace_links: list[dict[str, str]] = []
    private_path_markers: list[dict[str, str]] = []
    files = public_markdown_files(root)

    for source in files:
        text = source.read_text(encoding="utf-8")
        relative_source = source.relative_to(root).as_posix()
        for marker in _PRIVATE_PATH_MARKERS:
            if marker in text:
                private_path_markers.append(
                    {"source": relative_source, "marker": marker}
                )
        for match in _MARKDOWN_LINK.finditer(text):
            raw_target = match.group(1)
            target = _local_target(raw_target)
            if target is None:
                continue
            resolved = (source.parent / target).resolve()
            try:
                resolved.relative_to(root)
            except ValueError:
                outside_workspace_links.append(
                    {"source": relative_source, "target": raw_target}
                )
                continue
            if not resolved.exists():
                missing_links.append(
                    {"source": relative_source, "target": raw_target}
                )

    return {
        "ready": not (
            missing_links or outside_workspace_links or private_path_markers
        ),
        "file_count": len(files),
        "missing_links": missing_links,
        "outside_workspace_links": outside_workspace_links,
        "private_path_markers": private_path_markers,
        "uses_network": False,
        "reads_env_truth": False,
    }
