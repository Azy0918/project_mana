#!/usr/bin/env python3
"""Attach fixed character reference images to kamishibai generation manifests.

This tool makes the character sheet usable by image generation pipelines:

- Builds assets/character_generation_refs.json from assets/character_reference.json.
- Detects characters that appear in each scene/cut prompt.
- Adds characterIds, characterReferenceImages, and a reference instruction to
  scene_manifest*.json and visual_cut_plan*.json.

The image generator can then pass characterReferenceImages as IP-Adapter /
reference-image inputs, while keeping imagePrompt focused on the scene.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CHARACTER_REFERENCE = ROOT / "assets" / "character_reference.json"
GENERATION_REFS = ROOT / "assets" / "character_generation_refs.json"

REFERENCE_INSTRUCTION = (
    "Use characterReferenceImages as identity/design references. Preserve the "
    "same character, face, hairstyle, body type, outfit, and fixed prop design. "
    "Do not copy the reference sheet layout, labels, captions, or white margins. "
    "Change only expression, pose, camera angle, and scene composition."
)


EXTRA_ALIASES: dict[str, list[str]] = {
    "takumi": ["タクミ", "新人夜勤", "新人バイト"],
    "mina": ["ミナ", "先輩夜勤"],
    "future_worker_ep01": ["未来青年", "未来の店員", "未来の会社員", "返品済み青年", "長谷山"],
    "aseda_ryuji": ["汗田竜司", "汗田", "汗田リュウジ"],
    "zakiyama_tatsuya": ["座木山辰哉", "座木山", "崎山タツヤ"],
    "karasawa_eiji": ["唐沢栄治", "唐沢", "唐沢エイジ"],
    "thirteenth_register": ["第十三レジ", "13th register"],
    "navigation_terminal_ep02": ["ナビ端末", "バイクナビ", "ナビ"],
    "twelfth_register": ["第十二レジ"],
    "fourteenth_register": ["第十四レジ"],
    "truck_driver_ep04": ["トラック運転手", "運転手"],
}


@dataclass(frozen=True)
class CharacterRef:
    id: str
    name: str
    aliases: tuple[str, ...]
    image: str
    prompt: str
    must_keep: tuple[str, ...]
    must_avoid: tuple[str, ...]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def load_character_refs() -> list[CharacterRef]:
    data = load_json(CHARACTER_REFERENCE)
    refs: list[CharacterRef] = []
    for item in data.get("characters", []):
        cid = str(item["id"])
        aliases = {str(item.get("name", "")), str(item.get("kana", ""))}
        aliases.update(EXTRA_ALIASES.get(cid, []))
        aliases.discard("")
        refs.append(
            CharacterRef(
                id=cid,
                name=str(item.get("name", cid)),
                aliases=tuple(sorted(aliases, key=len, reverse=True)),
                image=str(item["image"]),
                prompt=str(item.get("prompt", "")),
                must_keep=tuple(str(x) for x in as_list(item.get("mustKeep"))),
                must_avoid=tuple(str(x) for x in as_list(item.get("mustAvoid"))),
            )
        )
    return refs


def build_generation_refs(refs: list[CharacterRef]) -> dict[str, Any]:
    return {
        "version": 1,
        "source": "assets/character_reference.json",
        "purpose": (
            "Reference-image map for 20 cuts x 12 episodes. Generation pipelines "
            "should attach these images when the corresponding characterIds appear."
        ),
        "referenceInstruction": REFERENCE_INSTRUCTION,
        "characters": [
            {
                "id": ref.id,
                "name": ref.name,
                "aliases": list(ref.aliases),
                "primaryImage": ref.image,
                "referenceImages": [
                    {
                        "role": "design_sheet",
                        "path": ref.image,
                        "weight": 1.0,
                    }
                ],
                "prompt": ref.prompt,
                "mustKeep": list(ref.must_keep),
                "mustAvoid": list(ref.must_avoid),
            }
            for ref in refs
        ],
    }


def manifest_files() -> list[Path]:
    files = sorted(ROOT.glob("scene_manifest*.json"))
    files.extend(sorted(ROOT.glob("visual_cut_plan*.json")))
    return files


def searchable_text(item: dict[str, Any]) -> str:
    keys = (
        "speaker",
        "dialogue",
        "visualCutTitle",
        "visualLabel",
        "progressLabel",
        "imagePrompt",
        "title",
        "prompt",
        "role",
        "name",
    )
    parts: list[str] = []
    for key in keys:
        value = item.get(key)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(v) for v in value)
    return "\n".join(parts)


def detect_character_ids(item: dict[str, Any], refs: list[CharacterRef]) -> list[str]:
    text = searchable_text(item)
    if not text:
        return []
    detected: list[str] = []
    for ref in refs:
        if any(alias and alias in text for alias in ref.aliases):
            detected.append(ref.id)
    return detected


def reference_images_for(ids: list[str], refs_by_id: dict[str, CharacterRef]) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    seen: set[str] = set()
    for cid in ids:
        ref = refs_by_id[cid]
        if ref.image in seen:
            continue
        seen.add(ref.image)
        images.append({"characterId": cid, "role": "design_sheet", "path": ref.image, "weight": 1.0})
    return images


def update_manifest(path: Path, refs: list[CharacterRef]) -> tuple[int, int]:
    data = load_json(path)
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON array")

    refs_by_id = {ref.id: ref for ref in refs}
    changed = 0
    with_refs = 0
    for item in data:
        if not isinstance(item, dict):
            continue
        ids = detect_character_ids(item, refs)
        images = reference_images_for(ids, refs_by_id)
        if ids:
            with_refs += 1
        before = (
            item.get("characterIds"),
            item.get("characterReferenceImages"),
            item.get("characterReferenceInstruction"),
        )
        item["characterIds"] = ids
        item["characterReferenceImages"] = images
        if ids:
            item["characterReferenceInstruction"] = REFERENCE_INSTRUCTION
        else:
            item.pop("characterReferenceInstruction", None)
        after = (
            item.get("characterIds"),
            item.get("characterReferenceImages"),
            item.get("characterReferenceInstruction"),
        )
        if before != after:
            changed += 1

    write_json(path, data)
    return changed, with_refs


def write_jobs_summary(refs: list[CharacterRef]) -> Path:
    rows: list[dict[str, Any]] = []
    refs_by_id = {ref.id: ref for ref in refs}
    for path in manifest_files():
        if not path.name.startswith("visual_cut_plan"):
            continue
        data = load_json(path)
        for item in data:
            if not isinstance(item, dict):
                continue
            ids = item.get("characterIds") or detect_character_ids(item, refs)
            rows.append(
                {
                    "plan": path.name,
                    "id": item.get("visualCutId"),
                    "visualCutId": item.get("visualCutId"),
                    "lineStart": item.get("lineStart"),
                    "lineEnd": item.get("lineEnd"),
                    "plannedImage": item.get("plannedImage") or item.get("image"),
                    "characterIds": ids,
                    "referenceImages": reference_images_for(ids, refs_by_id),
                    "imagePrompt": item.get("prompt") or item.get("imagePrompt"),
                }
            )
    out_dir = ROOT / "assets" / "generation_jobs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "character_reference_jobs.jsonl"
    out.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing manifests")
    parser.add_argument("--no-jobs", action="store_true", help="Do not write JSONL generation jobs")
    args = parser.parse_args()

    refs = load_character_refs()
    generation_refs = build_generation_refs(refs)
    if not args.dry_run:
        write_json(GENERATION_REFS, generation_refs)

    total_changed = 0
    total_with_refs = 0
    for path in manifest_files():
        if args.dry_run:
            data = load_json(path)
            with_refs = sum(1 for item in data if isinstance(item, dict) and detect_character_ids(item, refs))
            print(f"{path.relative_to(ROOT)}: would annotate {with_refs} entries")
            total_with_refs += with_refs
            continue
        changed, with_refs = update_manifest(path, refs)
        total_changed += changed
        total_with_refs += with_refs
        print(f"{path.relative_to(ROOT)}: changed={changed}, with_refs={with_refs}")

    if not args.dry_run and not args.no_jobs:
        jobs_path = write_jobs_summary(refs)
        print(f"wrote {jobs_path.relative_to(ROOT)}")

    print(f"total_changed={total_changed}, total_with_refs={total_with_refs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
