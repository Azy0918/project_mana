from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]

REQUIRED_RELEASE_FILES = [
    ".gitignore",
    "README.md",
    "requirements.txt",
    "app.py",
    "data/cards.csv",
    "src/db_bootstrap.py",
    "src/deck_generation_request.py",
    "src/deck_builder.py",
    "src/deck_condition_analyzer.py",
    "src/generated_deck_store.py",
    "src/generated_deck_analyzer.py",
    "src/release_readiness_checker.py",
    "src/release_report_exporter.py",
    "src/smoke_test_runner.py",
    "src/launch_report_exporter.py",
    "src/release_bundle_exporter.py",
    "src/release_manifest.py",
]

GENERATED_PATH_PREFIXES = [
    "data/exports/",
    "data/backups/",
]


def check_git_release_readiness(root_dir: Path = ROOT_DIR) -> dict[str, Any]:
    status_lines = _git_lines(["git", "status", "--short"], root_dir)
    branch = _git_text(["git", "branch", "--show-current"], root_dir)
    commit = _git_text(["git", "rev-parse", "--short", "HEAD"], root_dir)
    remote = _git_text(["git", "remote", "get-url", "origin"], root_dir)
    upstream = _git_text(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], root_dir)

    staged = [line for line in status_lines if line[:2].strip() and not line.startswith("??")]
    untracked = [line[3:] for line in status_lines if line.startswith("??")]
    generated_untracked = [
        path
        for path in untracked
        if any(_normalize(path).startswith(prefix) for prefix in GENERATED_PATH_PREFIXES)
    ]
    source_untracked = [
        path
        for path in untracked
        if path.endswith(".py") or path in REQUIRED_RELEASE_FILES
    ]
    missing_required = [path for path in REQUIRED_RELEASE_FILES if not (root_dir / path).exists()]

    issues: list[str] = []
    warnings: list[str] = []

    if not branch:
        issues.append("Gitブランチを取得できません。")
    if not remote:
        issues.append("origin remote が設定されていません。")
    if missing_required:
        issues.append("リリース必須ファイルが不足しています: " + ", ".join(missing_required))
    if source_untracked:
        warnings.append("未追跡のソース/必須ファイルがあります: " + ", ".join(source_untracked))
    if generated_untracked:
        warnings.append("未追跡の生成物があります。通常はcommit不要です: " + ", ".join(generated_untracked))

    ok = not issues
    return {
        "ok": ok,
        "status": "push準備OK" if ok else "要確認",
        "branch": branch,
        "commit": commit,
        "remote": remote,
        "upstream": upstream,
        "dirty": bool(status_lines),
        "staged_count": len(staged),
        "untracked_count": len(untracked),
        "status_lines": status_lines,
        "missing_required": missing_required,
        "source_untracked": source_untracked,
        "generated_untracked": generated_untracked,
        "issues": issues,
        "warnings": warnings,
        "suggested_commands": _suggested_commands(source_untracked),
    }


def _suggested_commands(source_untracked: list[str]) -> list[str]:
    files = REQUIRED_RELEASE_FILES + source_untracked
    unique_files = []
    for path in files:
        if path not in unique_files:
            unique_files.append(path)
    return [
        "git add " + " ".join(unique_files),
        'git commit -m "Prepare Project MANA release"',
        "git push origin main",
    ]


def _normalize(path: str) -> str:
    return path.replace("\\", "/")


def _git_text(command: list[str], cwd: Path) -> str:
    result = _run(command, cwd)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _git_lines(command: list[str], cwd: Path) -> list[str]:
    text = _git_text(command, cwd)
    return [line for line in text.splitlines() if line.strip()]


def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=5, check=False)
    except Exception as exc:
        return subprocess.CompletedProcess(command, returncode=1, stdout="", stderr=str(exc))
