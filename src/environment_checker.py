from __future__ import annotations

import importlib.metadata
import platform
import sys
from pathlib import Path
from typing import Any

from src.import_cards import DEFAULT_CSV_PATH, DEFAULT_DB_PATH, ROOT_DIR


REQUIRED_PACKAGES = ["streamlit", "openai", "python-dotenv"]


def check_python_environment() -> dict[str, Any]:
    return {
        "python_version": sys.version.split()[0],
        "python_executable": sys.executable,
        "platform": platform.platform(),
    }


def check_required_libraries(packages: list[str] | None = None) -> list[dict[str, Any]]:
    rows = []
    for package in packages or REQUIRED_PACKAGES:
        try:
            version = importlib.metadata.version(package)
            rows.append({"package": package, "installed": True, "version": version})
        except importlib.metadata.PackageNotFoundError:
            rows.append({"package": package, "installed": False, "version": ""})
    return rows


def check_streamlit_environment() -> dict[str, Any]:
    try:
        import streamlit as st

        version = st.__version__
        installed = True
    except Exception:
        version = ""
        installed = False
    return {"installed": installed, "version": version}


def check_data_paths(
    csv_path: Path = DEFAULT_CSV_PATH,
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    data_dir = ROOT_DIR / "data"
    return {
        "data_dir": str(data_dir),
        "data_dir_exists": data_dir.exists(),
        "csv_path": str(csv_path),
        "csv_exists": csv_path.exists(),
        "db_path": str(db_path),
        "db_exists": db_path.exists(),
    }


def collect_environment_report() -> dict[str, Any]:
    libraries = check_required_libraries()
    data_paths = check_data_paths()
    streamlit = check_streamlit_environment()
    warnings = []

    for library in libraries:
        if not library["installed"]:
            warnings.append(f'{library["package"]} がインストールされていません。')
    if not data_paths["data_dir_exists"]:
        warnings.append("data フォルダがありません。")
    if not data_paths["csv_exists"]:
        warnings.append("data/cards.csv がありません。")
    if not data_paths["db_exists"]:
        warnings.append("data/cards.db がありません。cards.csv から取り込みが必要です。")
    if not streamlit["installed"]:
        warnings.append("Streamlit が利用できません。")

    return {
        "python": check_python_environment(),
        "libraries": libraries,
        "streamlit": streamlit,
        "data_paths": data_paths,
        "warnings": warnings,
        "ok": not warnings,
    }
