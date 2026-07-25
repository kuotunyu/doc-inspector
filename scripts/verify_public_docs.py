"""Verify local links and privacy boundaries in public Markdown."""

from __future__ import annotations

import json
from pathlib import Path

from doc_inspector.docs_verify import verify_public_docs


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    report = verify_public_docs(root)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
