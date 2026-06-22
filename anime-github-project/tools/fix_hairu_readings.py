"""Force 入る-family readings from hiragana は to katakana ハ across all reading manifests.

`はい[っるりら]` (= 入って/入った/入る/入り/入ら read in all-hiragana) is replaced with
`ハい...` so AivisSpeech reads "ha-i" not the particle "wa". The audit confirmed this
pattern occurs ONLY on 入る lines, so a raw-text replace is safe and preserves formatting.
Prints every file it touches and the replacement count (expected total: 14).
"""
from __future__ import annotations
import glob
import os
import re

ASSETS = r"C:\Users\qvf03\OneDrive\ドキュメント\深夜二時の第十三レジ\13th-register-kamishibai\assets"
PAT = re.compile(r"はい([っるりら])")


def main() -> int:
    total = 0
    for f in sorted(glob.glob(os.path.join(ASSETS, "manifest_reading_hiragana_*.json"))):
        raw = open(f, encoding="utf-8").read()
        new, n = PAT.subn(r"ハい\1", raw)
        if n:
            open(f, "w", encoding="utf-8").write(new)
            total += n
            print(f"{os.path.basename(f)}: {n} replaced")
    print(f"TOTAL replacements: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
