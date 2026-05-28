from __future__ import annotations

import csv
import html
from io import StringIO
from typing import Any


def rows_to_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def markdown_to_html(markdown_text: str, title: str = "Project MANA 研究レポート") -> str:
    body_lines = []
    in_list = False

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        if not line:
            if in_list:
                body_lines.append("</ul>")
                in_list = False
            continue

        if line.startswith("# "):
            if in_list:
                body_lines.append("</ul>")
                in_list = False
            body_lines.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            if in_list:
                body_lines.append("</ul>")
                in_list = False
            body_lines.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("- "):
            if not in_list:
                body_lines.append("<ul>")
                in_list = True
            body_lines.append(f"<li>{html.escape(line[2:])}</li>")
        else:
            if in_list:
                body_lines.append("</ul>")
                in_list = False
            body_lines.append(f"<p>{html.escape(line)}</p>")

    if in_list:
        body_lines.append("</ul>")

    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.7; max-width: 920px; margin: 40px auto; padding: 0 20px; color: #1f2933; }}
    h1 {{ border-bottom: 2px solid #334e68; padding-bottom: 8px; }}
    h2 {{ margin-top: 28px; border-bottom: 1px solid #d9e2ec; padding-bottom: 4px; }}
    li {{ margin: 4px 0; }}
  </style>
</head>
<body>
{chr(10).join(body_lines)}
</body>
</html>
"""
