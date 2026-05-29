from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
import zipfile

import pandas as pd


REQUIRED_COLUMNS = [
    "card_id",
    "name",
    "civilization",
    "cost",
    "card_type",
    "power",
    "race",
    "text",
    "tags",
]


def load_cards(path: str | Path) -> pd.DataFrame:
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"CSVが見つかりません: {path}")

    df = pd.read_csv(path, dtype=str).fillna("")

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"必須列が不足しています: {missing}")

    return df


def export_completed_cards_csv(
    input_path: str | Path = "data/cards.csv",
    output_dir: str | Path = "data/exports",
) -> Path:
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = load_cards(input_path)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"cards_completed_{timestamp}.csv"

    df.to_csv(output_path, index=False, encoding="utf-8-sig")

    return output_path


def export_cards_summary(
    input_path: str | Path = "data/cards.csv",
    output_dir: str | Path = "data/exports",
) -> Path:
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = load_cards(input_path)

    summary = {
        "total_cards": len(df),
        "unique_names": df["name"].nunique(),
        "duplicate_names": len(df) - df["name"].nunique(),
        "civilizations": df["civilization"].value_counts().to_dict(),
        "card_types": df["card_type"].value_counts().to_dict(),
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"cards_summary_{timestamp}.txt"

    lines = []
    lines.append("Project MANA 仮カードDB サマリー")
    lines.append("=" * 40)
    lines.append(f"総カード数: {summary['total_cards']}")
    lines.append(f"ユニークカード名数: {summary['unique_names']}")
    lines.append(f"同名重複数: {summary['duplicate_names']}")
    lines.append("")
    lines.append("文明別カード数:")
    for key, value in summary["civilizations"].items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("カードタイプ別カード数:")
    for key, value in summary["card_types"].items():
        lines.append(f"- {key}: {value}")

    output_path.write_text("\n".join(lines), encoding="utf-8")

    return output_path


def export_completed_cards_zip(
    input_path: str | Path = "data/cards.csv",
    output_dir: str | Path = "data/exports",
) -> Path:
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = export_completed_cards_csv(input_path, output_dir)
    summary_path = export_cards_summary(input_path, output_dir)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = output_dir / f"project_mana_cards_completed_{timestamp}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(csv_path, arcname="cards_completed.csv")
        z.write(summary_path, arcname="cards_summary.txt")

    return zip_path


def replace_cards_with_completed_csv(
    completed_csv_path: str | Path,
    target_path: str | Path = "data/cards.csv",
) -> Path:
    completed_csv_path = Path(completed_csv_path)
    target_path = Path(target_path)

    if not completed_csv_path.exists():
        raise FileNotFoundError(f"完成版CSVが見つかりません: {completed_csv_path}")

    backup_dir = target_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"cards_before_replace_{timestamp}.csv"

    if target_path.exists():
        shutil.copy2(target_path, backup_path)

    shutil.copy2(completed_csv_path, target_path)

    return backup_path
