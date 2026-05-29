from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
from typing import Any


DEFAULT_EXPORT_DIR = Path("data") / "exports" / "launch_reports"


def build_launch_report(
    release_result: dict[str, Any],
    smoke_result: dict[str, Any],
) -> dict[str, Any]:
    launch_ok = bool(release_result.get("ok")) and bool(smoke_result.get("ok"))
    release_score = int(release_result.get("score", 0))
    smoke_passed = int(smoke_result.get("passed", 0))
    smoke_failed = int(smoke_result.get("failed", 0))
    smoke_total = smoke_passed + smoke_failed
    smoke_score = round(smoke_passed / smoke_total * 100) if smoke_total else 0

    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "launch_ok": launch_ok,
        "launch_status": "ローンチOK" if launch_ok else "要確認",
        "overall_score": round((release_score + smoke_score) / 2),
        "release": release_result,
        "smoke": smoke_result,
    }


def launch_report_to_markdown(report: dict[str, Any]) -> str:
    release = report.get("release", {})
    smoke = report.get("smoke", {})

    lines = [
        "# Project MANA 最終ローンチレポート",
        "",
        f"- 作成日時: {report.get('created_at')}",
        f"- ローンチ判定: {report.get('launch_status')}",
        f"- 総合スコア: {report.get('overall_score')} / 100",
        f"- 公開前診断: {release.get('status')} ({release.get('score')} / 100)",
        f"- スモークテスト: {smoke.get('status')} (成功 {smoke.get('passed')} / 失敗 {smoke.get('failed')})",
        "",
        "## 公開前診断",
        "",
        "| 項目 | 結果 | 判定 |",
        "| --- | --- | --- |",
    ]
    for row in release.get("checks", []):
        lines.append(f"| {row.get('項目', '')} | {row.get('結果', '')} | {row.get('判定', '')} |")

    lines.extend(["", "## スモークテスト", "", "| 項目 | 判定 | 詳細 |", "| --- | --- | --- |"])
    for row in smoke.get("rows", []):
        lines.append(f"| {row.get('項目', '')} | {row.get('判定', '')} | {row.get('詳細', '')} |")

    lines.extend(["", "## 問題", ""])
    issues = release.get("issues", [])
    failed_smoke = [row for row in smoke.get("rows", []) if row.get("判定") != "OK"]
    if issues or failed_smoke:
        for issue in issues:
            lines.append(f"- {issue}")
        for row in failed_smoke:
            lines.append(f"- スモークテスト失敗: {row.get('項目')} ({row.get('詳細')})")
    else:
        lines.append("- なし")

    lines.extend(["", "## 警告", ""])
    warnings = release.get("warnings", [])
    if warnings:
        for warning in warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- なし")

    lines.append("")
    return "\n".join(lines)


def export_launch_report(
    report: dict[str, Any],
    output_dir: str | Path = DEFAULT_EXPORT_DIR,
) -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    markdown_path = output_dir / f"launch_report_{timestamp}.md"
    json_path = output_dir / f"launch_report_{timestamp}.json"

    markdown_path.write_text(launch_report_to_markdown(report), encoding="utf-8")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "markdown": markdown_path,
        "json": json_path,
    }
