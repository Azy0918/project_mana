# -*- coding: utf-8 -*-
"""EP04改修版(2026-07-04): ep04_revised.md → scene_manifest_ep04.json 骨格を再構築。
- セリフ行を ep04_v001.. に採番(「通常レジSE：ピッ。」は音声化せずスキップ、SE挿入位置として報告)
- カット割りは既存 visual_cut_plan_ep04.json の20カットへ再割付(vc15/vc17は今回不使用)
- 画像=plan(planned実在ならplanned/無ければfallback)、imagePrompt=旧manifestからvc単位で継承
- start/end は 0 のまま → gen_episode_aivis.py ep04 が合成時に retime する
"""
import json
import re
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parents[1]
KAMI = REPO / "13th-register-kamishibai"
SCRIPT_MD = TOOLS.parent / "ep04_revised.md"
PLAN = KAMI / "visual_cut_plan_ep04.json"
OUT = KAMI / "scene_manifest_ep04.json"

# 声行番号(1始まり) → visualCutId。改修版の話のビートを既存20カットへ対応付け
CUT_START = {
    1: "vc01",   # マニュアルと予告紙
    5: "vc02",   # あと23分/唐揚げ棒1本
    14: "vc03",  # 第十三レジ出現
    18: "vc04",  # 未来レシート先行印字
    27: "vc05",  # 汗田登場・温度のズレ
    37: "vc06",  # 商品46度/未照合/温め直す?
    44: "vc07",  # 唐揚げ棒スキャン46度
    49: "vc08",  # リング展開・100キロ圏スキャン
    52: "vc09",  # 327名検知・絞れてない
    56: "vc10",  # トラック運転手来店・人間ピッ
    61: "vc11",  # 記憶温度72度・差分26度
    71: "vc12",  # 記憶温度合わせ・国道の街灯
    77: "vc13",  # 再発行・お詫び0件ありがとう1件
    83: "vc14",  # 受け渡し・一口・冷めてない
    89: "vc16",  # 退店・ありがとうございました
    91: "vc18",  # 最終レシート・再照合予定
    97: "vc19",  # レジ消滅・補充
    103: "vc20", # ノート追記・結論
}

# vc18=最終レシートの操作ログ(プレイヤーのレシートオーバーレイ)
LOG_BY_VC = {
    "vc18": [
        "未来クレーム　発生回避",
        "先行謝罪　未使用",
        "温め直し証明　一件",
        "返品済み青年　再照合予定",
    ],
}


def main() -> int:
    lines = []
    sfx_after = []  # 通常レジSE行の直前の声行id(=SE挿入位置)
    for raw in SCRIPT_MD.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        m = re.match(r"^([^：]+)：(.+)$", raw)
        if not m:
            continue
        speaker, text = m.group(1), m.group(2)
        if speaker == "通常レジSE":
            if lines:
                sfx_after.append(lines[-1][2])
            continue
        lines.append((speaker, text, f"ep04_v{len(lines)+1:03d}"))

    plan = {c["visualCutId"]: c for c in json.loads(PLAN.read_text(encoding="utf-8"))}
    old = json.loads(OUT.read_text(encoding="utf-8"))
    prompt_by_vc = {}
    for s in old:
        prompt_by_vc.setdefault(s["visualCutId"], s.get("imagePrompt", ""))

    total = len(lines)
    scenes = []
    vc = "vc01"
    fallback_first = ""
    for i, (speaker, text, line_id) in enumerate(lines, 1):
        vc = CUT_START.get(i, vc)
        c = plan[vc]
        n = int(vc[2:])
        title = c.get("title", vc)
        pi = (c.get("plannedImage") or "").split("?")[0]
        fb = (c.get("fallbackImage") or "").split("?")[0]
        img = pi if (pi and (KAMI / pi).exists()) else fb
        if not fallback_first:
            fallback_first = img
        log = LOG_BY_VC.get(vc) or [
            f"発話ログ　{i:02d}/{total}",
            f"担当　{speaker}",
        ]
        scenes.append({
            "id": line_id,
            "cut": f"ep04_{i:03d}",
            "visualCutId": vc,
            "visualCutTitle": title,
            "visualCutIndex": n,
            "start": 0.0,
            "end": 0.0,
            "image": img,
            "plannedImage": c.get("plannedImage", img),
            "fallbackImage": fallback_first,
            "imagePrompt": prompt_by_vc.get(vc, ""),
            "speaker": speaker,
            "dialogue": text,
            "reading": text,
            "log": log,
            "visualLabel": f"{n:02d}/20　{title}",
            "progressLabel": f"{i:02d}/{total}　{speaker}",
        })

    OUT.write_text(json.dumps(scenes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}  ({len(scenes)} scenes)")
    print("SE(sfx_scan)挿入位置:", ", ".join(sfx_after))
    reg = [s["id"] for s in scenes if s["dialogue"].startswith("第十三レジ。ただいま営業中")]
    print("レジ登場SE(sfx_register)挿入位置:", ", ".join(reg))
    used = sorted({s["visualCutId"] for s in scenes}, key=lambda v: int(v[2:]))
    print("使用カット:", ", ".join(used))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
