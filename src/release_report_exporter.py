from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
from typing import Any


DEFAULT_EXPORT_DIR = Path("data") / "exports" / "release_reports"


def release_readiness_to_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Project MANA 公開前診断レポート",
        "",
        f"- 作成日時: {datetime.now().isoformat(timespec='seconds')}",
        f"- 公開判定: {result.get('status')}",
        f"- リリーススコア: {result.get('score')} / 100",
        f"- 問題数: {len(result.get('issues', []))}",
        f"- 警告数: {len(result.get('warnings', []))}",
        "",
        "## チェック結果",
        "",
        "| 項目 | 結果 | 判定 |",
        "| --- | --- | --- |",
    ]

    for row in result.get("checks", []):
        lines.append(f"| {row.get('項目', '')} | {row.get('結果', '')} | {row.get('判定', '')} |")

    lines.extend(["", "## サンプル生成チェック", ""])
    sample = result.get("sample_generation", {})
    for key, value in sample.items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## 問題", ""])
    issues = result.get("issues", [])
    if issues:
        for issue in issues:
            lines.append(f"- {issue}")
    else:
        lines.append("- なし")

    lines.extend(["", "## 警告", ""])
    warnings = result.get("warnings", [])
    if warnings:
        for warning in warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- なし")

    lines.append("")
    return "\n".join(lines)


def export_release_readiness_report(
    result: dict[str, Any],
    output_dir: str | Path = DEFAULT_EXPORT_DIR,
) -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    markdown_path = output_dir / f"release_readiness_{timestamp}.md"
    json_path = output_dir / f"release_readiness_{timestamp}.json"

    markdown_path.write_text(release_readiness_to_markdown(result), encoding="utf-8")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "markdown": markdown_path,
        "json": json_path,
    }
