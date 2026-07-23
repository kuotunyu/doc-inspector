"""Generate local-only, watermarked synthetic demo documents."""

from __future__ import annotations

import argparse
from pathlib import Path

from doc_inspector.demo import generate_demo_artifacts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data") / "demo" / "generated",
    )
    args = parser.parse_args()
    artifacts = generate_demo_artifacts(args.output)
    for artifact in artifacts:
        print(f"{artifact.name}: {artifact.expected_level} {artifact.image_path}")


if __name__ == "__main__":
    main()
