from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_EXPORT_DIR = Path("data") / "exports" / "deployment_runbooks"


def build_streamlit_cloud_runbook(
    git_check: dict[str, Any],
    release_result: dict[str, Any] | None = None,
    smoke_result: dict[str, Any] | None = None,
    launch_report: dict[str, Any] | None = None,
) -> str:
    release_result = release_result or {}
    smoke_result = smoke_result or {}
    launch_report = launch_report or {}

    lines = [
        "# Project MANA Streamlit Cloud デプロイ手順書",
        "",
        f"- 作成日時: {datetime.now().isoformat(timespec='seconds')}",
        f"- Git branch: {git_check.get('branch') or '-'}",
        f"- Git commit: {git_check.get('commit') or '-'}",
        f"- origin: {git_check.get('remote') or '-'}",
        f"- push準備: {git_check.get('status') or '-'}",
        f"- 公開前診断: {release_result.get('status') or '未実行'}",
        f"- スモークテスト: {smoke_result.get('status') or '未実行'}",
        f"- ローンチ判定: {launch_report.get('launch_status') or '未作成'}",
        "",
        "## 1. ローカル最終確認",
        "",
        "- データ保守画面で公開前リリース診断を実行する",
        "- データ保守画面でスモークテストを実行する",
        "- 最終ローンチレポートを作成する",
        "- リリース成果物ZIPを作成する",
        "- GitHub push準備チェックを実行する",
        "",
        "## 2. GitHubへpush",
        "",
        "```powershell",
    ]
    lines.extend(git_check.get("suggested_commands", []))
    lines.extend(
        [
            "```",
            "",
            "## 3. Streamlit Cloudで再起動",
            "",
            "- Streamlit Cloudの対象アプリを開く",
            "- 最新commitが反映されているか確認する",
            "- 必要なら `Reboot app` または `Clear cache and rerun` を実行する",
            "",
            "## 4. 公開サイト確認",
            "",
            "- ダッシュボードの登録カード数が `1250` になっていること",
            "- デッキ生成画面で条件付きデッキ生成が動くこと",
            "- データ保守画面で公開前リリース診断が `公開OK` になること",
            "- データ保守画面でスモークテストが `OK` になること",
            "",
            "## 5. 異常時の戻し方",
            "",
            "- GitHubで直前commitへ戻す、または修正commitを追加する",
            "- Streamlit Cloudで再起動する",
            "- `data/cards.csv` が1250件版か確認する",
            "- `data/cards.db` は公開環境でCSVから自動再作成されるため、DBファイルの手動配置は不要",
            "",
            "## 現在のgit status",
            "",
            "```text",
            "\n".join(git_check.get("status_lines", [])) or "clean",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def export_streamlit_cloud_runbook(
    markdown: str,
    output_dir: str | Path = DEFAULT_EXPORT_DIR,
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"streamlit_cloud_deploy_runbook_{timestamp}.md"
    output_path.write_text(markdown, encoding="utf-8")
    return output_path
