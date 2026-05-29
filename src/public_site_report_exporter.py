from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
from typing import Any


DEFAULT_EXPORT_DIR = Path("data") / "exports" / "public_site_reports"


def public_site_check_to_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Project MANA 公開URL確認レポート",
        "",
        f"- 作成日時: {datetime.now().isoformat(timespec='seconds')}",
        f"- URL: {result.get('url') or '-'}",
        f"- 状態: {result.get('status')}",
        f"- HTTPステータス: {result.get('status_code') or '-'}",
        f"- 取得文字数: {result.get('content_length')}",
        "",
        "## キーワード確認",
        "",
        "| キーワード | 初期HTML内 |",
        "| --- | --- |",
    ]

    for keyword, hit in result.get("keyword_hits", {}).items():
        lines.append(f"| {keyword} | {'あり' if hit else 'なし'} |")

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


def export_public_site_report(
    result: dict[str, Any],
    output_dir: str | Path = DEFAULT_EXPORT_DIR,
) -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    markdown_path = output_dir / f"public_site_check_{timestamp}.md"
    json_path = output_dir / f"public_site_check_{timestamp}.json"

    markdown_path.write_text(public_site_check_to_markdown(result), encoding="utf-8")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "markdown": markdown_path,
        "json": json_path,
    }
