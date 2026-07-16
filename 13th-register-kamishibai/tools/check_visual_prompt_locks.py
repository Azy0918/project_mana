#!/usr/bin/env python3
"""Check visual prompts for stale character lock text.

This is intentionally small and conservative. It catches old prompt fragments
that have already caused wrong image generation, without trying to judge every
creative detail in a cut.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

ZAKIYAMA_REQUIRED = (
    "短く刈った黒白混じりの髪",
    "チェックシャツ",
    "オリーブの釣りベスト",
)

ZAKIYAMA_STALE_PHRASES = (
    "夜釣り帰りの常連",
    "夜釣り常連姿",
    "夜釣り好きの変わりもの",
    "短く乱れた黒髪、眠そうで少し開いた目、薄い眉、薄い無精髭と口髭",
    "下唇が少し前に出て上唇を隠す",
    "服は暗いフーディー、ポケットの多いカーキの釣りベスト",
    "オリーブ色のカーゴパンツ、黒い長靴",
    "小道具は長い釣り竿、リール、タモ網、バケツ",
    "釣り竿と古い地図",
)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def positive_zakiyama_prompt(text: str) -> bool:
    positive_markers = ("座木山が", "座木山辰哉が", "座木山は", "座木山辰哉は")
    negative_markers = ("似せない", "のような", "にしない", "禁止")
    if not any(marker in text for marker in positive_markers):
        return False
    return not all(marker in text for marker in negative_markers)


def check_visual_plan(path: Path) -> list[str]:
    data = load_json(path)
    errors: list[str] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        prompt = str(item.get("prompt") or item.get("imagePrompt") or "")
        label = str(item.get("visualCutId") or item.get("id") or f"row{index + 1}")
        stale_hits = [phrase for phrase in ZAKIYAMA_STALE_PHRASES if phrase in prompt]
        for phrase in stale_hits:
            errors.append(f"{path.name}:{label}: stale Zakiyama phrase: {phrase}")
        if positive_zakiyama_prompt(prompt):
            missing = [phrase for phrase in ZAKIYAMA_REQUIRED if phrase not in prompt]
            for phrase in missing:
                errors.append(f"{path.name}:{label}: missing current Zakiyama lock: {phrase}")
    return errors


def main() -> int:
    errors: list[str] = []
    for path in sorted(ROOT.glob("visual_cut_plan*.json")):
        errors.extend(check_visual_plan(path))

    if errors:
        print("visual prompt lock check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("visual prompt lock check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
