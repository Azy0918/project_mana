import csv
import json
from pathlib import Path


OUT_PATHS = [
    Path("13th-register-kamishibai/visual_cut_plan.json"),
    Path("site/visual_cut_plan.json"),
]
CSV_PATHS = [
    Path("13th-register-kamishibai/assets/ep01_visual_cut_plan.csv"),
    Path("site/assets/ep01_visual_cut_plan.csv"),
]

REGISTER_FACE_STYLE = (
    "第十三レジの顔つきは、黒く重いセルフレジ端末の斜めスクリーンに、"
    "ネオンシアンの短い水平な目が二本、小さな水平の口が一つだけ光る無表情フェイス。"
    "かわいくしすぎず、眠そうで機械的、でも妙に意思がある。"
    "本体は黒い金属とガラス、角ばった筐体、カード端末とスキャナー付き。"
)


VISUAL_CUTS = [
    {
        "visualCutId": "vc01",
        "lineStart": "ep01_v001",
        "lineEnd": "ep01_v002",
        "title": "深夜コンビニ外観",
        "plannedImage": "assets/scenes/planned/ep01_vc01_store_exterior.jpg",
        "fallbackImage": "assets/scenes/scene_01_opening.jpg",
        "prompt": "午前二時三分、国道沿いの日本のコンビニ外観。冷たい青い照明、誰もいない駐車場、静かなSFコメディの始まり。",
    },
    {
        "visualCutId": "vc02",
        "lineStart": "ep01_v003",
        "lineEnd": "ep01_v004",
        "title": "おにぎり棚の前のタクミ",
        "plannedImage": "assets/scenes/planned/ep01_vc02_takumi_onigiri_shelf.jpg",
        "fallbackImage": "assets/scenes/scene_02_onigiri_shelf.jpg",
        "prompt": "おにぎり棚の前で廃棄シールを見比べるタクミ。新人夜勤バイト、困惑顔。横に冷静なミナ。",
    },
    {
        "visualCutId": "vc03",
        "lineStart": "ep01_v005",
        "lineEnd": "ep01_v010",
        "title": "廃棄おにぎり問答",
        "plannedImage": "assets/scenes/planned/ep01_vc03_onigiri_banter.jpg",
        "fallbackImage": "assets/scenes/scene_02_onigiri_shelf.jpg",
        "prompt": "ミナが淡々と注意し、タクミがツッコむ。おにぎり棚、値札、廃棄時間シール。静かな会話コメディ。",
    },
    {
        "visualCutId": "vc04",
        "lineStart": "ep01_v011",
        "lineEnd": "ep01_v014",
        "title": "第十三レジ出現前兆",
        "plannedImage": "assets/scenes/planned/ep01_vc04_register_appears.png",
        "fallbackImage": "assets/scenes/scene_03_register.jpg",
        "prompt": f"雑誌棚とコピー機の間に第十三レジが現れる瞬間。空間が少し歪み、タクミが固まる。{REGISTER_FACE_STYLE}",
    },
    {
        "visualCutId": "vc05",
        "lineStart": "ep01_v015",
        "lineEnd": "ep01_v020",
        "title": "営業中の第十三レジ",
        "plannedImage": "assets/scenes/planned/ep01_vc05_register_talks.png",
        "fallbackImage": "assets/scenes/scene_03_register.jpg",
        "prompt": f"第十三レジが営業中表示を出す。タクミは驚き、ミナは当然のように無表情。{REGISTER_FACE_STYLE}",
    },
    {
        "visualCutId": "vc06",
        "lineStart": "ep01_v022",
        "lineEnd": "ep01_v024",
        "title": "未来の会社員来店",
        "plannedImage": "assets/scenes/planned/ep01_vc06_future_worker_enters.jpg",
        "fallbackImage": "assets/scenes/scene_04_future_worker_enters.jpg",
        "prompt": "くたびれたスーツ姿の未来の会社員が入店。肩の小型液晶、首元の透明パッチ、疲労感。",
    },
    {
        "visualCutId": "vc07",
        "lineStart": "ep01_v025",
        "lineEnd": "ep01_v030",
        "title": "五十年後の返品相談",
        "plannedImage": "assets/scenes/planned/ep01_vc07_future_return_counter.jpg",
        "fallbackImage": "assets/scenes/scene_04_future_worker_enters.jpg",
        "prompt": "レジ前で未来の会社員が返品を頼む。ミナは通常接客、タクミは対応マニュアルを探す。",
    },
    {
        "visualCutId": "vc08",
        "lineStart": "ep01_v031",
        "lineEnd": "ep01_v036",
        "title": "未来おにぎりスキャン",
        "plannedImage": "assets/scenes/planned/ep01_vc08_future_onigiri_scan.jpg",
        "fallbackImage": "assets/scenes/scene_05_future_onigiri_scan.jpg",
        "prompt": f"完全栄養おにぎり・思い出の鮭を第十三レジでスキャン。警告表示、人類生存率、タクミの焦り。{REGISTER_FACE_STYLE}",
    },
    {
        "visualCutId": "vc09",
        "lineStart": "ep01_v037",
        "lineEnd": "ep01_v041",
        "title": "始末書を気にする未来人",
        "plannedImage": "assets/scenes/planned/ep01_vc09_future_worker_excuse.jpg",
        "fallbackImage": "assets/scenes/scene_04_future_worker_enters.jpg",
        "prompt": "未来の会社員が始末書を気にしている。タクミが引き気味にツッコミ、ミナは静観。",
    },
    {
        "visualCutId": "vc10",
        "lineStart": "ep01_v042",
        "lineEnd": "ep01_v047",
        "title": "時空返品メニュー",
        "plannedImage": "assets/scenes/planned/ep01_vc10_time_return_menu.jpg",
        "fallbackImage": "assets/scenes/scene_05_future_onigiri_scan.jpg",
        "prompt": f"第十三レジの画面に、通常返品、時空返品、存在取消、温める、店長呼出のメニューが並ぶ。{REGISTER_FACE_STYLE}",
    },
    {
        "visualCutId": "vc11",
        "lineStart": "ep01_v048",
        "lineEnd": "ep01_v051",
        "title": "残り三分と七万二千円",
        "plannedImage": "assets/scenes/planned/ep01_vc11_countdown_cost.jpg",
        "fallbackImage": "assets/scenes/scene_05_future_onigiri_scan.jpg",
        "prompt": f"第十三レジのカウントダウン、仕入れ原価七万二千円表示。タクミが即座に返品を決意する。{REGISTER_FACE_STYLE}",
    },
    {
        "visualCutId": "vc12",
        "lineStart": "ep01_v052",
        "lineEnd": "ep01_v056",
        "title": "世界の分岐をレンジへ",
        "plannedImage": "assets/scenes/planned/ep01_vc12_microwave_choice.jpg",
        "fallbackImage": "assets/scenes/scene_06_microwave.jpg",
        "prompt": "ミナが温め確認をし、未来おにぎりが電子レンジへ。タクミが全力でツッコむ。",
    },
    {
        "visualCutId": "vc13",
        "lineStart": "ep01_v058",
        "lineEnd": "ep01_v062",
        "title": "電子レンジ内の未来映像",
        "plannedImage": "assets/scenes/planned/ep01_vc13_microwave_future_vision.jpg",
        "fallbackImage": "assets/scenes/scene_06_microwave.jpg",
        "prompt": "電子レンジの光の中に未来の食堂、空っぽの棚、長い列、子どもがおにぎりを持って笑う映像。",
    },
    {
        "visualCutId": "vc14",
        "lineStart": "ep01_v063",
        "lineEnd": "ep01_v068",
        "title": "履歴メモ入力",
        "plannedImage": "assets/scenes/planned/ep01_vc14_history_memo.jpg",
        "fallbackImage": "assets/scenes/scene_07_receipt.jpg",
        "prompt": f"第十三レジに履歴メモ入力欄。ミナの雑なメモが記録され、タクミが驚く。{REGISTER_FACE_STYLE}",
    },
    {
        "visualCutId": "vc15",
        "lineStart": "ep01_v069",
        "lineEnd": "ep01_v073",
        "title": "時空返品完了とコーヒー",
        "plannedImage": "assets/scenes/planned/ep01_vc15_refund_coffee.jpg",
        "fallbackImage": "assets/scenes/scene_07_receipt.jpg",
        "prompt": f"返品完了、返金百六十八円。未来の会社員がホットコーヒーを買い、タクミが未来に行きたくなくなる。背景に第十三レジ。{REGISTER_FACE_STYLE}",
    },
    {
        "visualCutId": "vc16",
        "lineStart": "ep01_v074",
        "lineEnd": "ep01_v079",
        "title": "第十三レジ消滅とレシート",
        "plannedImage": "assets/scenes/planned/ep01_vc16_receipt_result.jpg",
        "fallbackImage": "assets/scenes/scene_07_receipt.jpg",
        "prompt": f"午前二時二十分、第十三レジが消えかけ、長いレシートだけが残る。人類生存率微増、スタッフ割引対象外。{REGISTER_FACE_STYLE}",
    },
    {
        "visualCutId": "vc17",
        "lineStart": "ep01_v081",
        "lineEnd": "ep01_v083",
        "title": "座木山辰哉、コピー機へ",
        "plannedImage": "assets/scenes/planned/ep01_vc17_zakiyama_copy.jpg",
        "fallbackImage": "assets/scenes/scene_08_back_to_normal.jpg",
        "prompt": "眠そうな常連、座木山辰哉が古いツーリング地図を抱えてコピー機へ。長めの黒髪、濃い髭、バイクジャケット。",
    },
    {
        "visualCutId": "vc18",
        "lineStart": "ep01_v084",
        "lineEnd": "ep01_v085",
        "title": "夜勤だから",
        "plannedImage": "assets/scenes/planned/ep01_vc18_night_shift_answer.jpg",
        "fallbackImage": "assets/scenes/scene_08_back_to_normal.jpg",
        "prompt": "タクミが普通のお客も変なのかと聞き、ミナが『夜勤だから』と無表情で返す。店内は平常運転。",
    },
    {
        "visualCutId": "vc19",
        "lineStart": "ep01_v086",
        "lineEnd": "ep01_v086",
        "title": "世界が少しだけ救われる",
        "plannedImage": "assets/scenes/planned/ep01_vc19_world_saved_quietly.jpg",
        "fallbackImage": "assets/scenes/scene_08_back_to_normal.jpg",
        "prompt": "世界が少しだけ救われた余韻。深夜コンビニ店内、タクミとミナ、静かな青い光。大事件の後でも普通。",
    },
    {
        "visualCutId": "vc20",
        "lineStart": "ep01_v087",
        "lineEnd": "ep01_v087",
        "title": "夜勤はまだ終わらない",
        "plannedImage": "assets/scenes/planned/ep01_vc20_chores_remain.jpg",
        "fallbackImage": "assets/scenes/scene_08_back_to_normal.jpg",
        "prompt": "床清掃、雑誌返品、廃棄登録が残っている深夜コンビニ。タクミが遠い目、ミナは淡々。余韻のラスト。",
    },
]


def main() -> None:
    for out_path in OUT_PATHS:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(VISUAL_CUTS, ensure_ascii=False, indent=2), encoding="utf-8")
        print(out_path)

    fields = [
        "visualCutId",
        "lineStart",
        "lineEnd",
        "title",
        "plannedImage",
        "fallbackImage",
        "prompt",
    ]
    for csv_path in CSV_PATHS:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(VISUAL_CUTS)
        print(csv_path)


if __name__ == "__main__":
    main()
