from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
from typing import Any


DEFAULT_EXPORT_DIR = Path("data") / "exports" / "release_checklists"


def release_checklist_to_markdown(checklist: dict[str, Any]) -> str:
    lines = [
        "# Project MANA リリースチェックリスト",
        "",
        f"- 作成日時: {datetime.now().isoformat(timespec='seconds')}",
        f"- 状態: {checklist.get('status')}",
        f"- 必須完了: {checklist.get('required_done')} / {checklist.get('required_count')}",
        f"- 全体完了: {checklist.get('done_count')} / {checklist.get('total_count')}",
        "",
        "| 項目 | 状態 | 詳細 |",
        "| --- | --- | --- |",
    ]
    for item in checklist.get("items", []):
        lines.append(f"| {item.get('項目', '')} | {item.get('状態', '')} | {item.get('詳細', '')} |")
    lines.append("")
    return "\n".join(lines)


def export_release_checklist(
    checklist: dict[str, Any],
    output_dir: str | Path = DEFAULT_EXPORT_DIR,
) -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    markdown_path = output_dir / f"release_checklist_{timestamp}.md"
    json_path = output_dir / f"release_checklist_{timestamp}.json"

    markdown_path.write_text(release_checklist_to_markdown(checklist), encoding="utf-8")
    json_path.write_text(json.dumps(checklist, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "markdown": markdown_path,
        "json": json_path,
    }
