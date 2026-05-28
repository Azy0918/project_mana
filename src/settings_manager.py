from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from src.ai_deck_builder import DEFAULT_MODEL
from src.backup_manager import DEFAULT_BACKUP_DIR
from src.import_cards import DEFAULT_CSV_PATH, DEFAULT_DB_PATH, ROOT_DIR


ENV_PATH = ROOT_DIR / ".env"


def load_app_settings() -> dict[str, Any]:
    load_dotenv(ENV_PATH)
    api_key = os.getenv("OPENAI_API_KEY", "")
    model = os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
    return {
        "root_dir": ROOT_DIR,
        "csv_path": DEFAULT_CSV_PATH,
        "db_path": DEFAULT_DB_PATH,
        "backup_dir": DEFAULT_BACKUP_DIR,
        "data_dir": ROOT_DIR / "data",
        "env_path": ENV_PATH,
        "env_exists": ENV_PATH.exists(),
        "openai_api_key_configured": bool(api_key.strip()),
        "openai_api_key_hint": mask_secret(api_key),
        "openai_model": model,
    }


def mask_secret(value: str) -> str:
    if not value:
        return "未設定"
    if len(value) <= 8:
        return "設定済み"
    return f"{value[:4]}...{value[-4:]}"


def env_creation_guide() -> str:
    return "\n".join(
        [
            "プロジェクト直下に `.env` を作成します。",
            "",
            "```env",
            "OPENAI_API_KEY=your_api_key_here",
            "OPENAI_MODEL=gpt-5-mini",
            "```",
            "",
            "`OPENAI_API_KEY` はコードやREADMEへ直接書かず、`.env` にだけ保存してください。",
        ]
    )


def setup_guide() -> list[str]:
    return [
        "Python仮想環境を作成します。",
        "`pip install -r requirements.txt` で必要ライブラリを入れます。",
        "`python src/import_cards.py` で `data/cards.db` を作成します。",
        "AIデッキ生成を使う場合は `.env` に `OPENAI_API_KEY` を設定します。",
        "`streamlit run app.py` でアプリを起動します。",
    ]
