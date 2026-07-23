"""Secret-safe static verification for the public release handoff."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "README.md",
    "LICENSE",
    "DEPLOYMENT.md",
    "PRODUCT.md",
    "Dockerfile",
    ".dockerignore",
    ".env.example",
    "pyproject.toml",
    "uv.lock",
    "docs/UI_AUDIT.md",
    "docs/REMOTE_SETUP.md",
    "scripts/check_live_space.py",
    "scripts/serve_ui_fixture.py",
    "docs/assets/browser-report.json",
    "docs/assets/ui-quality-audit.json",
    "docs/assets/result-red.png",
)

REMOTE_SETUP_MARKERS = (
    "GitHub 主倉 → Hugging Face 部署鏡像",
    "https://github.com/kuotunyu/doc-inspector",
    "https://huggingface.co/spaces/steven0226/doc-inspector",
    "PUBLIC_MAX_REQUESTS_PER_HOUR=60",
    "scripts/check_live_space.py",
    "私人驗收清單",
    "回復方式",
    "Set-Location '<專案資料夾>'",
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
    "維護者整體驗收",
    "Hugging Face Docker Space",
    "118 passed，總 coverage 89%",
    "https://steven0226-doc-inspector.hf.space",
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

    readme = (root / "README.md").read_text(encoding="utf-8")
    missing_readme_markers = [
        marker for marker in README_MARKERS if marker not in readme
    ]
    remote_setup = (root / "docs" / "REMOTE_SETUP.md").read_text(encoding="utf-8")
    missing_remote_setup_markers = [
        marker for marker in REMOTE_SETUP_MARKERS if marker not in remote_setup
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
            (root / "DEPLOYMENT.md").read_text(encoding="utf-8"),
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
        + missing_readme_markers
        + missing_remote_setup_markers
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
        "missing_readme_markers": missing_readme_markers,
        "missing_remote_setup_markers": missing_remote_setup_markers,
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
    report = build_release_report()
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ready_for_manual_handoff"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
