from __future__ import annotations

import shutil
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from src.import_cards import DEFAULT_CSV_PATH, DEFAULT_DB_PATH, ROOT_DIR


DEFAULT_BACKUP_DIR = ROOT_DIR / "data" / "backups"


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_backup_dir(backup_dir: Path = DEFAULT_BACKUP_DIR) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def backup_csv(
    csv_path: Path = DEFAULT_CSV_PATH,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
) -> Path:
    backup_dir = ensure_backup_dir(backup_dir)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSVが見つかりません: {csv_path}")
    backup_path = backup_dir / f"{csv_path.stem}_{timestamp()}{csv_path.suffix}"
    shutil.copy2(csv_path, backup_path)
    return backup_path


def backup_database(
    db_path: Path = DEFAULT_DB_PATH,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
) -> Path:
    backup_dir = ensure_backup_dir(backup_dir)
    if not db_path.exists():
        raise FileNotFoundError(f"DBが見つかりません: {db_path}")

    backup_path = backup_dir / f"{db_path.stem}_{timestamp()}{db_path.suffix}"
    source = sqlite3.connect(db_path)
    destination = sqlite3.connect(backup_path)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    return backup_path


def create_backup_zip(
    data_dir: Path | None = None,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
) -> Path:
    root_data_dir = data_dir or (ROOT_DIR / "data")
    backup_dir = ensure_backup_dir(backup_dir)
    zip_path = backup_dir / f"project_mana_backup_{timestamp()}.zip"
    include_suffixes = {".csv", ".db", ".md", ".html", ".json", ".txt"}

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in root_data_dir.rglob("*"):
            if not path.is_file() or path == zip_path:
                continue
            if path.suffix.lower() not in include_suffixes:
                continue
            archive.write(path, path.relative_to(ROOT_DIR))

    return zip_path


def list_backups(backup_dir: Path = DEFAULT_BACKUP_DIR) -> list[dict[str, Any]]:
    backup_dir = ensure_backup_dir(backup_dir)
    rows = []
    for path in sorted(backup_dir.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
        if not path.is_file():
            continue
        rows.append(
            {
                "name": path.name,
                "path": str(path),
                "size_kb": round(path.stat().st_size / 1024, 1),
                "updated_at": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return rows


def read_backup_bytes(path: str | Path) -> bytes:
    return Path(path).read_bytes()


def restore_guide() -> list[str]:
    return [
        "アプリを停止します。",
        "`data/cards.csv` を戻す場合は、対象のCSVバックアップを `data/cards.csv` にコピーします。",
        "`data/cards.db` を戻す場合は、対象のDBバックアップを `data/cards.db` にコピーします。",
        "ZIPバックアップから戻す場合は、必要なファイルだけを展開して上書きします。",
        "復元後にアプリを起動し、データ保守画面で健全性チェックを実行します。",
    ]
