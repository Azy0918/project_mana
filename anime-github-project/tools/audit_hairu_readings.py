"""Audit reading manifests for 入る-family words whose reading starts with は.

When 入る/入って/入った/入り/入ら is written in all-hiragana (はいる/はいって/...),
AivisSpeech can mis-read the leading は as the topic particle "wa". Forcing カタカナ ハ
(ハいって) fixes it. This lists every such spot so we can decide which to fix.
"""
from __future__ import annotations
import glob
import json
import os
import re

ASSETS = r"C:\Users\qvf03\OneDrive\ドキュメント\深夜二時の第十三レジ\13th-register-kamishibai\assets"
RISK = re.compile(r"はい[っるりら]")   # 入る-family read with hiragana は (mis-read risk)
FIXED = re.compile(r"ハい")            # already forced to katakana ハ
IRU_KANJI = ("入っ", "入る", "入り", "入ら")


def main() -> int:
    files = sorted(glob.glob(os.path.join(ASSETS, "manifest_reading_hiragana_*.json")))
    risk, fixed, other = [], [], []
    for f in files:
        ep = os.path.basename(f).replace("manifest_reading_hiragana_", "").replace(".json", "")
        for e in json.loads(open(f, encoding="utf-8").read()):
            text, syn, _id = e.get("text", ""), e.get("synthesis_text", ""), e.get("id", "")
            has_iru = any(k in text for k in IRU_KANJI)
            if RISK.search(syn):
                risk.append((ep, _id, text, syn))
            elif FIXED.search(syn) and has_iru:
                fixed.append((ep, _id, text, syn))
            elif "入" in text:
                other.append((ep, _id, text, syn))

    print("=" * 70)
    print(f"[RISK] reading still hiragana 'はい~' : {len(risk)} lines")
    print("=" * 70)
    for ep, _id, text, syn in risk:
        print(f"[{ep}] {_id}\n   text: {text}\n   read: {syn}\n")

    print("=" * 70)
    print(f"[FIXED] katakana 'ハ' already applied : {len(fixed)} lines")
    print("=" * 70)
    for ep, _id, text, syn in fixed:
        print(f"[{ep}] {_id}  read: {syn}")

    print()
    print("=" * 70)
    print(f"[OTHER] other 入-words (should NOT be はいる) : {len(other)} lines")
    print("=" * 70)
    for ep, _id, text, syn in other:
        print(f"[{ep}] {_id}  text: {text}\n        read: {syn}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
