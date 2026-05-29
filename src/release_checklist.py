from __future__ import annotations

from pathlib import Path
from typing import Any


def build_release_checklist(state: dict[str, Any]) -> dict[str, Any]:
    release = state.get("release_readiness")
    smoke = state.get("smoke_test")
    launch = state.get("launch_report")
    git_check = state.get("git_release_check")
    public_check = state.get("public_site_check")
    bundle_path = state.get("release_bundle_path")

    items = [
        _item("公開前リリース診断", bool(release and release.get("ok")), _detail_status(release)),
        _item("スモークテスト", bool(smoke and smoke.get("ok")), _detail_status(smoke)),
        _item("最終ローンチレポート", bool(launch and launch.get("launch_ok")), launch.get("launch_status") if launch else "未作成"),
        _item("リリース成果物ZIP", _path_exists(bundle_path), str(bundle_path) if bundle_path else "未作成"),
        _item("GitHub push準備", bool(git_check and git_check.get("ok")), _detail_status(git_check)),
        _item("公開URL確認", bool(public_check and public_check.get("ok")), _detail_status(public_check)),
    ]
    done_count = sum(1 for item in items if item["完了"])
    required_count = 5
    required_done = sum(1 for item in items[:5] if item["完了"])
    ready = required_done == required_count

    return {
        "ready": ready,
        "status": "リリース準備完了" if ready else "未完了あり",
        "done_count": done_count,
        "total_count": len(items),
        "required_done": required_done,
        "required_count": required_count,
        "items": items,
    }


def _item(name: str, done: bool, detail: str) -> dict[str, Any]:
    return {
        "項目": name,
        "状態": "完了" if done else "未完了",
        "完了": done,
        "詳細": detail,
    }


def _detail_status(value: dict[str, Any] | None) -> str:
    if not value:
        return "未実行"
    return str(value.get("status") or value.get("launch_status") or "-")


def _path_exists(value: Any) -> bool:
    if not value:
        return False
    try:
        return Path(value).exists()
    except TypeError:
        return False
