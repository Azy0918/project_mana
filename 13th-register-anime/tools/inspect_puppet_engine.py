from __future__ import annotations

import argparse
import csv
from pathlib import Path

from puppet_motion_engine import create_default_engine, create_engine_from_json


ROOT = Path(__file__).resolve().parent
DEFAULT_OUT = ROOT / "output_video" / "puppet_engine_rigs.csv"
WIDTH = 1280
HEIGHT = 720


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Puppet/Vtuber風モーションエンジンのリグ一覧を出力します。")
    parser.add_argument("--csv", default=str(DEFAULT_OUT), help="CSV出力先")
    parser.add_argument("--rig-json", default="", help="外部JSONリグを使う場合に指定")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_path = Path(args.csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine_from_json(WIDTH, HEIGHT, Path(args.rig_json)) if args.rig_json else create_default_engine(WIDTH, HEIGHT)
    rows = engine.describe()
    with out_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["image_name", "patches", "motion_scales", "face", "blink_times", "mouth"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(out_path)
    for row in rows:
        print(f"{row['image_name']}: patches={row['patches']} motion_scales={row['motion_scales']} face={row['face']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
