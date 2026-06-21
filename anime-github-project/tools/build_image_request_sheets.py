"""Generate Codex-facing image request sheets (画像生成依頼票) for EP05-EP12.

Reads each `13th-register-kamishibai/assets/manifest_reading_hiragana_epNN.json`
(Claude's finalized line IDs + cut grouping + dialogue) and emits
`epNN_image_request_sheet.md` at the repo root: one section per cut, listing the
characters present, narration lines (= scene/action cues) and dialogue (= subtitles).

This is the Claude->Codex handoff: final line IDs + dialogue + cut plan + must/forbid.
Codex builds `image_assignment_epNN.json` and the actual images from this.
Run: python anime-github-project/tools/build_image_request_sheets.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "13th-register-kamishibai" / "assets"

TITLES = {
    "05": "昭和の伝票、まだ未処理です",
    "06": "賞味期限が生まれる前のパン",
    "07": "宇宙宅配便、店留めです",
    "08": "月面店、発注しすぎました",
    "09": "銀河ポイントカードはお持ちですか？",
    "10": "あの会社員、返品済みです",
    "11": "第十二レジと第十四レジ",
    "12": "午前二時十七分、通常営業です",
}

SPEC = """## スタイル・制約（全カット共通）
- 詳細アニメ／ビジュアルノベルCG調・アニメ塗り・セルルック。フラット／ベクター／ミニマル調にしない。
- 人物のビジュアルは `13th-register-kamishibai/character_visual_locks.json` の lock に厳密準拠。各カットの生成プロンプトに、そのカットの「登場」人物全員分の lockPrompt を必ず含める。
- レジは混同しない: 第十三レジ＝黒いセルフレジ・斜め画面にシアンの横目2本＋小さな口。第十二レジ＝昭和の木目調／くすんだベージュの古いレジ。第十四レジ＝透明アクリル・白と淡い紫の光の未来型。
- 9:16 縦。`object-fit:cover` 前提。上端の角（話数バッジ・切替・再生状態）と下部30〜40%（字幕ドック＋シークバー）に重要要素を置かない。
- 画像内に字幕・UI文字・時計の数字を焼き込まない。
- 保存先: `13th-register-kamishibai/assets/scenes/planned/` に下記カットIDで `epNN_vcNN_説明.png`。"""


def build(nn: str, title: str) -> str:
    entries = json.loads((ASSETS / f"manifest_reading_hiragana_ep{nn}.json").read_text(encoding="utf-8"))
    order: list[str] = []
    by_cut: dict[str, list[dict]] = {}
    for e in entries:
        cut = e["cut"]
        if cut not in by_cut:
            by_cut[cut] = []
            order.append(cut)
        by_cut[cut].append(e)

    out: list[str] = []
    out.append(f"# 第{int(nn)}話 画像生成依頼票「{title}」")
    out.append("")
    out.append("Claude が台本・読み・音声・最終行IDを確定済み。**画像生成と `image_assignment_ep" + nn + ".json` はあなた（Codex）の担当**。")
    out.append("各カット＝縦型ビジュアル1枚。地の文（ナレーション）が場面・動作の指定、セリフは字幕（画像に焼き込まない）。")
    out.append("")
    out.append(SPEC)
    out.append("")
    out.append(f"- 総行数: {len(entries)} ／ カット数: {len(order)}")
    out.append("- 音声・タイミングは合成済み。完了後 Claude が image_assignment 確認→scene_manifest生成→`?v`更新→公開を担当。")
    out.append("")
    for cut in order:
        es = by_cut[cut]
        chars: list[str] = []
        for e in es:
            ch = e["character"]
            if ch != "ナレーション" and ch not in chars:
                chars.append(ch)
        out.append(f"## {cut}")
        out.append(f"登場: {'、'.join(chars) if chars else '（人物なし：物・レジ・店内など）'}")
        for e in es:
            if e["character"] == "ナレーション":
                out.append(f"- （地の文）{e['text']}　[{e['id']}]")
            else:
                out.append(f"- {e['character']}「{e['text']}」　[{e['id']}]")
        out.append("")
    return "\n".join(out)


def main() -> int:
    for nn, title in TITLES.items():
        text = build(nn, title)
        dest = ROOT / f"ep{nn}_image_request_sheet.md"
        dest.write_text(text, encoding="utf-8")
        print(f"wrote {dest.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
