from __future__ import annotations

import argparse
from pathlib import Path

from puppet_motion_engine import export_default_rig_json


ROOT = Path(__file__).resolve().parent
DEFAULT_OUT = ROOT / "puppet_rigs" / "default_puppet_rigs.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="現在のデフォルトPuppet/VtuberリグをJSONに書き出します。")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="JSON出力先")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_path = Path(args.out)
    export_default_rig_json(out_path)
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
