from __future__ import annotations

from datetime import datetime
from pathlib import Path
import subprocess
from typing import Any

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[1]


def build_release_manifest(
    release_result: dict[str, Any],
    smoke_result: dict[str, Any],
    launch_report: dict[str, Any],
) -> dict[str, Any]:
    return {
        "app_name": "Project MANA",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "launch_status": launch_report.get("launch_status"),
        "overall_score": launch_report.get("overall_score"),
        "release_status": release_result.get("status"),
        "release_score": release_result.get("score"),
        "smoke_status": smoke_result.get("status"),
        "smoke_passed": smoke_result.get("passed"),
        "smoke_failed": smoke_result.get("failed"),
        "cards_csv_count": _count_cards_csv(ROOT_DIR / "data" / "cards.csv"),
        "git_commit": _git_output(["git", "rev-parse", "HEAD"]),
        "git_branch": _git_output(["git", "branch", "--show-current"]),
        "git_dirty": bool(_git_output(["git", "status", "--short"])),
        "included_files": [
            "data/cards.csv",
            "README.md",
            "requirements.txt",
            "reports/cards_summary.txt",
            "reports/release_readiness.md",
            "reports/release_readiness.json",
            "reports/smoke_test.json",
            "reports/launch_report.md",
            "reports/launch_report.json",
            "reports/release_manifest.json",
            "reports/release_manifest.md",
        ],
    }


def release_manifest_to_markdown(manifest: dict[str, Any]) -> str:
    lines = [
        "# Project MANA リリースマニフェスト",
        "",
        f"- 作成日時: {manifest.get('generated_at')}",
        f"- ローンチ判定: {manifest.get('launch_status')}",
        f"- 総合スコア: {manifest.get('overall_score')} / 100",
        f"- cards.csv 件数: {manifest.get('cards_csv_count')}",
        f"- Git branch: {manifest.get('git_branch') or 'unknown'}",
        f"- Git commit: {manifest.get('git_commit') or 'unknown'}",
        f"- 未コミット変更あり: {'yes' if manifest.get('git_dirty') else 'no'}",
        "",
        "## 同梱ファイル",
        "",
    ]
    for item in manifest.get("included_files", []):
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def _count_cards_csv(path: Path) -> int:
    if not path.exists():
        return 0
    return int(len(pd.read_csv(path, dtype=str).fillna("")))


def _git_output(command: list[str]) -> str:
    try:
        result = subprocess.run(
            command,
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()
