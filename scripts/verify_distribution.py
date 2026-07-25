"""Verify built release archives and import the wheel from an isolated target."""

from __future__ import annotations

from email.parser import Parser
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
PROJECT_NAME = "doc-inspector"
PACKAGE_NAME = "doc_inspector"
PROJECT_SUMMARY = "政府補助申請表單與收據的智慧抽取及送件前預檢工具"
PROJECT_URLS = {
    "Documentation": "https://github.com/kuotunyu/doc-inspector#readme",
    "Homepage": "https://github.com/kuotunyu/doc-inspector",
    "Issue Tracker": "https://github.com/kuotunyu/doc-inspector/issues",
    "Live Demo": "https://steven0226-doc-inspector.hf.space",
    "Repository": "https://github.com/kuotunyu/doc-inspector",
}

FORBIDDEN_PARTS = {
    ".agents",
    ".git",
    ".venv",
    "CLAUDE.md",
    "PLAN.md",
    "PROGRESS.md",
}
FORBIDDEN_SUBPATHS = {
    ("data", "benchmark"),
    ("data", "demo", "generated"),
    ("data", "raw"),
    ("logs",),
    ("outputs",),
}


def _project_version() -> str:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(pyproject["project"]["version"])


def _archive_parts(name: str) -> tuple[str, ...]:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"不安全的 archive path：{name}")
    return path.parts


def _forbidden_archive_entries(names: list[str], *, strip_root: bool) -> list[str]:
    forbidden: list[str] = []
    for name in names:
        parts = _archive_parts(name)
        relative = parts[1:] if strip_root and parts else parts
        if any(part in FORBIDDEN_PARTS for part in relative):
            forbidden.append(name)
            continue
        if relative and relative[-1] == ".env":
            forbidden.append(name)
            continue
        if any(relative[: len(prefix)] == prefix for prefix in FORBIDDEN_SUBPATHS):
            forbidden.append(name)
    return forbidden


def _verify_wheel(wheel: Path, version: str) -> dict[str, object]:
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        forbidden = _forbidden_archive_entries(names, strip_root=False)
        metadata_name = f"{PACKAGE_NAME}-{version}.dist-info/METADATA"
        metadata = Parser().parsestr(archive.read(metadata_name).decode("utf-8"))

    required_entries = {
        f"{PACKAGE_NAME}/__init__.py",
        f"{PACKAGE_NAME}/schemas.py",
        f"{PACKAGE_NAME}/service.py",
        metadata_name,
    }
    missing_entries = sorted(required_entries - set(names))
    metadata_issues: list[str] = []
    if metadata.get("Name") != PROJECT_NAME:
        metadata_issues.append("Name")
    if metadata.get("Version") != version:
        metadata_issues.append("Version")
    if str(metadata.get("Summary")) != PROJECT_SUMMARY:
        metadata_issues.append("Summary")
    if metadata.get("Requires-Python") != "<3.12,>=3.11":
        metadata_issues.append("Requires-Python")
    if "LICENSE" not in metadata.get_all("License-File", []):
        metadata_issues.append("License-File")
    project_urls = {}
    for item in metadata.get_all("Project-URL", []):
        label, separator, url = item.partition(", ")
        if separator:
            project_urls[label] = url
    if project_urls != PROJECT_URLS:
        metadata_issues.append("Project-URL")
    classifiers = set(metadata.get_all("Classifier", []))
    if {
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.11",
    } - classifiers:
        metadata_issues.append("Classifier")
    keywords = set((metadata.get("Keywords") or "").split(","))
    if {"document-ai", "document-validation", "taiwan"} - keywords:
        metadata_issues.append("Keywords")

    return {
        "file": wheel.name,
        "entry_count": len(names),
        "missing_entries": missing_entries,
        "forbidden_entries": forbidden,
        "metadata_issues": metadata_issues,
    }


def _verify_sdist(sdist: Path, version: str) -> dict[str, object]:
    expected_root = f"{PACKAGE_NAME}-{version}"
    with tarfile.open(sdist, mode="r:gz") as archive:
        names = archive.getnames()

    roots = sorted({parts[0] for name in names if (parts := _archive_parts(name))})
    forbidden = _forbidden_archive_entries(names, strip_root=True)
    required_entries = {
        f"{expected_root}/LICENSE",
        f"{expected_root}/README.md",
        f"{expected_root}/pyproject.toml",
        f"{expected_root}/src/{PACKAGE_NAME}/__init__.py",
    }
    missing_entries = sorted(required_entries - set(names))
    return {
        "file": sdist.name,
        "entry_count": len(names),
        "roots": roots,
        "expected_root": expected_root,
        "root_matches": roots == [expected_root],
        "missing_entries": missing_entries,
        "forbidden_entries": forbidden,
    }


def _wheel_import_smoke(wheel: Path, version: str) -> dict[str, object]:
    uv = shutil.which("uv")
    if uv is None:
        return {"passed": False, "error": "找不到 uv"}

    with tempfile.TemporaryDirectory(prefix="doc-inspector-wheel-smoke-") as target:
        target_path = Path(target).resolve()
        venv_path = target_path / "venv"
        environment = os.environ.copy()
        environment["UV_OFFLINE"] = "1"
        create_venv = subprocess.run(
            [
                uv,
                "venv",
                "--python",
                sys.executable,
                str(venv_path),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
        )
        if create_venv.returncode != 0:
            return {
                "passed": False,
                "stage": "create_venv",
                "error": create_venv.stderr.strip() or create_venv.stdout.strip(),
            }

        venv_python = (
            venv_path / "Scripts" / "python.exe"
            if sys.platform == "win32"
            else venv_path / "bin" / "python"
        )
        export_lock = subprocess.run(
            [
                uv,
                "export",
                "--frozen",
                "--no-dev",
                "--no-emit-project",
                "--no-hashes",
                "--no-header",
                "--no-annotate",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
        )
        if export_lock.returncode != 0:
            return {
                "passed": False,
                "stage": "export_lock",
                "error": export_lock.stderr.strip() or export_lock.stdout.strip(),
            }
        requirements = target_path / "requirements.txt"
        requirements.write_text(export_lock.stdout, encoding="utf-8")

        install_dependencies = subprocess.run(
            [
                uv,
                "pip",
                "install",
                "--python",
                str(venv_python),
                "--requirement",
                str(requirements),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
        )
        if install_dependencies.returncode != 0:
            return {
                "passed": False,
                "stage": "install_dependencies",
                "error": (
                    install_dependencies.stderr.strip()
                    or install_dependencies.stdout.strip()
                ),
            }

        install_wheel = subprocess.run(
            [
                uv,
                "pip",
                "install",
                "--python",
                str(venv_python),
                "--no-deps",
                str(wheel),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
        )
        if install_wheel.returncode != 0:
            return {
                "passed": False,
                "stage": "install_wheel",
                "error": install_wheel.stderr.strip() or install_wheel.stdout.strip(),
            }

        smoke_code = (
            "import importlib.metadata as metadata, json, pathlib;"
            "import doc_inspector;"
            "from doc_inspector.schemas import SchemaRegistry;"
            "print(json.dumps({"
            "'version': metadata.version('doc-inspector'),"
            "'module_path': str(pathlib.Path(doc_inspector.__file__).resolve()),"
            "'schema_names': sorted(SchemaRegistry.names())"
            "}))"
        )
        import_wheel = subprocess.run(
            [str(venv_python), "-I", "-c", smoke_code],
            cwd=target_path,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
        )
        if import_wheel.returncode != 0:
            return {
                "passed": False,
                "stage": "import_wheel",
                "error": import_wheel.stderr.strip() or import_wheel.stdout.strip(),
            }

        payload = json.loads(import_wheel.stdout.strip().splitlines()[-1])
        module_path = Path(payload["module_path"]).resolve()
        schema_names = payload["schema_names"]
        module_loaded_from_venv = module_path.is_relative_to(venv_path)
        passed = (
            payload["version"] == version
            and module_loaded_from_venv
            and set(schema_names) == {"subsidy_application", "receipt"}
        )
        return {
            "passed": passed,
            "installed_version": payload["version"],
            "module_loaded_from_venv": module_loaded_from_venv,
            "schema_names": schema_names,
            "dependencies_installed_offline": True,
        }


def build_distribution_report() -> dict[str, object]:
    version = _project_version()
    expected_wheel = DIST / f"{PACKAGE_NAME}-{version}-py3-none-any.whl"
    expected_sdist = DIST / f"{PACKAGE_NAME}-{version}.tar.gz"
    artifacts = sorted(path.name for path in DIST.glob("*") if path.name != ".gitignore")
    expected_artifacts = sorted((expected_wheel.name, expected_sdist.name))
    artifact_set_matches = artifacts == expected_artifacts

    wheel_report = (
        _verify_wheel(expected_wheel, version)
        if expected_wheel.is_file()
        else {"file": expected_wheel.name, "missing": True}
    )
    sdist_report = (
        _verify_sdist(expected_sdist, version)
        if expected_sdist.is_file()
        else {"file": expected_sdist.name, "missing": True}
    )
    import_smoke = (
        _wheel_import_smoke(expected_wheel, version)
        if expected_wheel.is_file()
        else {"passed": False, "error": "wheel 不存在"}
    )
    archive_issues = [
        issue
        for report in (wheel_report, sdist_report)
        for key in ("missing_entries", "forbidden_entries", "metadata_issues")
        for issue in report.get(key, [])
    ]
    if sdist_report.get("root_matches") is False:
        archive_issues.append("sdist root")

    passed = artifact_set_matches and not archive_issues and import_smoke.get("passed") is True
    return {
        "passed": passed,
        "project_version": version,
        "artifacts": artifacts,
        "expected_artifacts": expected_artifacts,
        "artifact_set_matches": artifact_set_matches,
        "wheel": wheel_report,
        "sdist": sdist_report,
        "wheel_import_smoke": import_smoke,
        "uses_network": False,
        "reads_env_truth": False,
    }


def main() -> int:
    report = build_distribution_report()
    print(json.dumps(report, ensure_ascii=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
