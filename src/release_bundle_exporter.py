from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import zipfile
from typing import Any

from src.card_db_exporter import export_cards_summary
from src.launch_report_exporter import launch_report_to_markdown
from src.release_manifest import build_release_manifest, release_manifest_to_markdown
from src.release_report_exporter import release_readiness_to_markdown


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_EXPORT_DIR = ROOT_DIR / "data" / "exports" / "release_bundles"


def export_release_bundle(
    release_result: dict[str, Any],
    smoke_result: dict[str, Any],
    launch_report: dict[str, Any],
    output_dir: str | Path = DEFAULT_EXPORT_DIR,
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = output_dir / f"project_mana_release_bundle_{timestamp}.zip"
    summary_path = export_cards_summary(ROOT_DIR / "data" / "cards.csv", output_dir)

    release_markdown = release_readiness_to_markdown(release_result)
    launch_markdown = launch_report_to_markdown(launch_report)
    manifest = build_release_manifest(release_result, smoke_result, launch_report)
    manifest_markdown = release_manifest_to_markdown(manifest)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        _write_if_exists(z, ROOT_DIR / "data" / "cards.csv", "data/cards.csv")
        _write_if_exists(z, ROOT_DIR / "README.md", "README.md")
        _write_if_exists(z, ROOT_DIR / "requirements.txt", "requirements.txt")
        z.write(summary_path, arcname="reports/cards_summary.txt")
        z.writestr("reports/release_readiness.md", release_markdown)
        z.writestr("reports/release_readiness.json", json.dumps(release_result, ensure_ascii=False, indent=2))
        z.writestr("reports/smoke_test.json", json.dumps(smoke_result, ensure_ascii=False, indent=2))
        z.writestr("reports/launch_report.md", launch_markdown)
        z.writestr("reports/launch_report.json", json.dumps(launch_report, ensure_ascii=False, indent=2))
        z.writestr("reports/release_manifest.md", manifest_markdown)
        z.writestr("reports/release_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    return zip_path


def _write_if_exists(z: zipfile.ZipFile, source_path: Path, arcname: str) -> None:
    if source_path.exists():
        z.write(source_path, arcname=arcname)
