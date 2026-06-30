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

TAKUMI_STYLE = (
    "タクミは全カットで同一人物。20歳前後の新人夜勤バイト、短い黒髪、細身、少し猫背、"
    "コンビニ制服と名札「タクミ」。驚き・困惑・ツッコミ顔が基本。"
)

MINA_STYLE = (
    "エリは全カットで同一人物。20代前半の先輩夜勤バイト、黒髪ボブまたは低いひとつ結び、"
    "コンビニ制服と名札「エリ」。淡々とした無表情、背筋がまっすぐ。"
)

FUTURE_WORKER_STYLE = (
    "未来青年 / 未来の会社員は全カットで同一人物として固定。キャラID: future_worker_ep01。"
    "2074年の食品流通管理課の若い男性会社員、実年齢27歳だが過労で40代手前に見える。"
    "細身で肩が落ちた体型、短く乱れた黒髪、疲れた目、目の下の薄いクマ、弱った困り顔。"
    "くたびれた濃紺スーツ、緩んだネクタイ、白シャツ、肩の小型液晶に残業時間表示、"
    "首元に透明な記憶返品タグ/絆創膏状パッチがあり中の銀色回路が淡く光る。"
    "小道具は未来おにぎり、未来レシート、ホットコーヒー。"
    "毎カットで顔立ち、髪型、体格、スーツ、首元タグを変えない。"
    "別人化禁止。眼鏡禁止。長髪禁止。濃い髭禁止。スポーツサングラス禁止。バイクジャケット禁止。"
    "座木山辰哉や汗田竜司に似せない。未来警察やサイバー戦士にしない。"
)

ZAKIYAMA_STYLE = (
    "座木山辰哉は55歳の近所の常連客で、未来人ではない。コピー機と古いツーリング地図の人。"
    "短めで寝ぐせ混じりの黒髪、丸い薄色レンズの眼鏡、片側だけ少しテープで補修された眼鏡、"
    "薄い無精髭、眠そうで焦点が少しずれた目、肩の力が抜けた立ち姿。"
    "服はくたっとした古いワークジャケット、色褪せたチェックシャツ、ゆるいカーディガン、"
    "首から古いコピーカードや小さな方位磁石、ポケットから折れた地図と付箋が少しはみ出す。"
    "古いツーリング地図を筒ではなく何度も折った状態で抱え、端に手書きの矢印や謎のメモがある。"
    "普通の常連なのに、どこか変わりもの。本人は大事件に気づいていない穏やかな奇妙さ。"
    "未来的装備、スーツ、肩液晶、首元タグ、長髪、濃い髭、スポーツサングラス、バイクジャケットは禁止。"
    "未来青年や汗田竜司に似せない。実在人物そっくりにしない。"
)

ANIME_STYLE_LOCK = (
    "2Dアニメイラスト、ビジュアルノベル風、ゲーム立ち絵風、アニメ塗り、セルルック、"
    "線画がはっきりしたキャラクターデザイン、非写実的。人物をフォトリアルにしない。"
)


def prompt_with_locks(base: str, *locks: str) -> str:
    return " ".join([base, *locks, ANIME_STYLE_LOCK])


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
        "prompt": prompt_with_locks(
            "おにぎり棚の前で廃棄シールを見比べるタクミ。横に冷静なエリ。",
            TAKUMI_STYLE,
            MINA_STYLE,
        ),
    },
    {
        "visualCutId": "vc03",
        "lineStart": "ep01_v005",
        "lineEnd": "ep01_v010",
        "title": "廃棄おにぎり問答",
        "plannedImage": "assets/scenes/planned/ep01_vc03_onigiri_banter.jpg",
        "fallbackImage": "assets/scenes/scene_02_onigiri_shelf.jpg",
        "prompt": prompt_with_locks(
            "エリが淡々と注意し、タクミがツッコむ。おにぎり棚、値札、廃棄時間シール。静かな会話コメディ。",
            TAKUMI_STYLE,
            MINA_STYLE,
        ),
    },
    {
        "visualCutId": "vc04",
        "lineStart": "ep01_v011",
        "lineEnd": "ep01_v014",
        "title": "第十三レジ出現前兆",
        "plannedImage": "assets/scenes/planned/ep01_vc04_register_appears.jpg",
        "fallbackImage": "assets/scenes/scene_03_register.jpg",
        "prompt": prompt_with_locks(
            f"雑誌棚とコピー機の間に第十三レジが現れる瞬間。空間が少し歪み、タクミが固まる。{REGISTER_FACE_STYLE}",
            TAKUMI_STYLE,
        ),
    },
    {
        "visualCutId": "vc05",
        "lineStart": "ep01_v015",
        "lineEnd": "ep01_v020",
        "title": "営業中の第十三レジ",
        "plannedImage": "assets/scenes/planned/ep01_vc05_register_talks.jpg",
        "fallbackImage": "assets/scenes/scene_03_register.jpg",
        "prompt": prompt_with_locks(
            f"第十三レジが営業中表示を出す。タクミは驚き、エリは当然のように無表情。{REGISTER_FACE_STYLE}",
            TAKUMI_STYLE,
            MINA_STYLE,
        ),
    },
    {
        "visualCutId": "vc06",
        "lineStart": "ep01_v022",
        "lineEnd": "ep01_v024",
        "title": "未来の会社員来店",
        "plannedImage": "assets/scenes/planned/ep01_vc06_future_worker_enters.jpg",
        "fallbackImage": "assets/scenes/scene_04_future_worker_enters.jpg",
        "prompt": prompt_with_locks(
            "自動ドアから未来青年 / 未来の会社員が入店する。深夜コンビニ店内、タクミとエリが迎える。",
            FUTURE_WORKER_STYLE,
            TAKUMI_STYLE,
            MINA_STYLE,
        ),
    },
    {
        "visualCutId": "vc07",
        "lineStart": "ep01_v025",
        "lineEnd": "ep01_v030",
        "title": "五十年後の返品相談",
        "plannedImage": "assets/scenes/planned/ep01_vc07_future_return_counter.jpg",
        "fallbackImage": "assets/scenes/scene_04_future_worker_enters.jpg",
        "prompt": prompt_with_locks(
            "レジ前で未来青年 / 未来の会社員が返品を頼む。エリは通常接客、タクミは対応マニュアルを探す。",
            FUTURE_WORKER_STYLE,
            TAKUMI_STYLE,
            MINA_STYLE,
        ),
    },
    {
        "visualCutId": "vc08",
        "lineStart": "ep01_v031",
        "lineEnd": "ep01_v036",
        "title": "未来おにぎりスキャン",
        "plannedImage": "assets/scenes/planned/ep01_vc08_future_onigiri_scan.jpg",
        "fallbackImage": "assets/scenes/scene_05_future_onigiri_scan.jpg",
        "prompt": prompt_with_locks(
            f"未来青年 / 未来の会社員が持参した完全栄養おにぎり・思い出の鮭を第十三レジでスキャン。警告表示、人類生存率、タクミの焦り。{REGISTER_FACE_STYLE}",
            FUTURE_WORKER_STYLE,
            TAKUMI_STYLE,
            MINA_STYLE,
        ),
    },
    {
        "visualCutId": "vc09",
        "lineStart": "ep01_v037",
        "lineEnd": "ep01_v041",
        "title": "始末書を気にする未来人",
        "plannedImage": "assets/scenes/planned/ep01_vc09_future_worker_excuse.jpg",
        "fallbackImage": "assets/scenes/scene_04_future_worker_enters.jpg",
        "prompt": prompt_with_locks(
            "未来青年 / 未来の会社員が始末書を気にして深く頭を下げる。タクミが引き気味にツッコミ、エリは静観。",
            FUTURE_WORKER_STYLE,
            TAKUMI_STYLE,
            MINA_STYLE,
        ),
    },
    {
        "visualCutId": "vc10",
        "lineStart": "ep01_v042",
        "lineEnd": "ep01_v047",
        "title": "時空返品メニュー",
        "plannedImage": "assets/scenes/planned/ep01_vc10_time_return_menu.jpg",
        "fallbackImage": "assets/scenes/scene_05_future_onigiri_scan.jpg",
        "prompt": prompt_with_locks(
            f"第十三レジの画面に、通常返品、時空返品、存在取消、温める、店長呼出のメニューが並ぶ。未来青年 / 未来の会社員は同じ顔で不安そうに見守る。{REGISTER_FACE_STYLE}",
            FUTURE_WORKER_STYLE,
            TAKUMI_STYLE,
            MINA_STYLE,
        ),
    },
    {
        "visualCutId": "vc11",
        "lineStart": "ep01_v048",
        "lineEnd": "ep01_v051",
        "title": "残り三分と七万二千円",
        "plannedImage": "assets/scenes/planned/ep01_vc11_countdown_cost.jpg",
        "fallbackImage": "assets/scenes/scene_05_future_onigiri_scan.jpg",
        "prompt": prompt_with_locks(
            f"第十三レジのカウントダウン、仕入れ原価七万二千円表示。タクミが即座に返品を決意し、未来青年 / 未来の会社員は同じ姿で気まずそうに立つ。{REGISTER_FACE_STYLE}",
            FUTURE_WORKER_STYLE,
            TAKUMI_STYLE,
            MINA_STYLE,
        ),
    },
    {
        "visualCutId": "vc12",
        "lineStart": "ep01_v052",
        "lineEnd": "ep01_v056",
        "title": "世界の分岐をレンジへ",
        "plannedImage": "assets/scenes/planned/ep01_vc12_microwave_choice.jpg",
        "fallbackImage": "assets/scenes/scene_06_microwave.jpg",
        "prompt": prompt_with_locks(
            "エリが温め確認をし、未来おにぎりが電子レンジへ。未来青年 / 未来の会社員は同じ顔でお願いしますと言い、タクミが全力でツッコむ。",
            FUTURE_WORKER_STYLE,
            TAKUMI_STYLE,
            MINA_STYLE,
        ),
    },
    {
        "visualCutId": "vc13",
        "lineStart": "ep01_v058",
        "lineEnd": "ep01_v062",
        "title": "電子レンジ内の未来映像",
        "plannedImage": "assets/scenes/planned/ep01_vc13_microwave_future_vision.jpg",
        "fallbackImage": "assets/scenes/scene_06_microwave.jpg",
        "prompt": prompt_with_locks(
            "電子レンジの光の中に未来の食堂、空っぽの棚、長い列、子どもがおにぎりを持って笑う映像。手前に同一人物の未来青年 / 未来の会社員が息を呑む。",
            FUTURE_WORKER_STYLE,
        ),
    },
    {
        "visualCutId": "vc14",
        "lineStart": "ep01_v063",
        "lineEnd": "ep01_v068",
        "title": "履歴メモ入力",
        "plannedImage": "assets/scenes/planned/ep01_vc14_history_memo.jpg",
        "fallbackImage": "assets/scenes/scene_07_receipt.jpg",
        "prompt": f"第十三レジに履歴メモ入力欄。エリの雑なメモが記録され、タクミが驚く。{REGISTER_FACE_STYLE}",
    },
    {
        "visualCutId": "vc15",
        "lineStart": "ep01_v069",
        "lineEnd": "ep01_v073",
        "title": "時空返品完了とコーヒー",
        "plannedImage": "assets/scenes/planned/ep01_vc15_refund_coffee.jpg",
        "fallbackImage": "assets/scenes/scene_07_receipt.jpg",
        "prompt": prompt_with_locks(
            f"返品完了、返金百六十八円。同一人物の未来青年 / 未来の会社員がホットコーヒーを買い、タクミが未来に行きたくなくなる。背景に第十三レジ。{REGISTER_FACE_STYLE}",
            FUTURE_WORKER_STYLE,
            TAKUMI_STYLE,
            MINA_STYLE,
        ),
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
        "prompt": prompt_with_locks(
            "眠そうな常連、座木山辰哉が古いツーリング地図を抱えてコピー機へ向かう。コピー機の光、深夜コンビニ、タクミが固まる。",
            ZAKIYAMA_STYLE,
            TAKUMI_STYLE,
            MINA_STYLE,
        ),
    },
    {
        "visualCutId": "vc18",
        "lineStart": "ep01_v084",
        "lineEnd": "ep01_v085",
        "title": "夜勤だから",
        "plannedImage": "assets/scenes/planned/ep01_vc18_night_shift_answer.jpg",
        "fallbackImage": "assets/scenes/scene_08_back_to_normal.jpg",
        "prompt": prompt_with_locks(
            "タクミが普通のお客も変なのかと聞き、エリが『夜勤だから』と無表情で返す。奥に座木山辰哉がコピー機で古い地図を白黒コピーしている。店内は平常運転。",
            TAKUMI_STYLE,
            MINA_STYLE,
            ZAKIYAMA_STYLE,
        ),
    },
    {
        "visualCutId": "vc19",
        "lineStart": "ep01_v086",
        "lineEnd": "ep01_v086",
        "title": "世界が少しだけ救われる",
        "plannedImage": "assets/scenes/planned/ep01_vc19_world_saved_quietly.jpg",
        "fallbackImage": "assets/scenes/scene_08_back_to_normal.jpg",
        "prompt": "世界が少しだけ救われた余韻。深夜コンビニ店内、タクミとエリ、静かな青い光。大事件の後でも普通。",
    },
    {
        "visualCutId": "vc20",
        "lineStart": "ep01_v087",
        "lineEnd": "ep01_v087",
        "title": "夜勤はまだ終わらない",
        "plannedImage": "assets/scenes/planned/ep01_vc20_chores_remain.jpg",
        "fallbackImage": "assets/scenes/scene_08_back_to_normal.jpg",
        "prompt": "床清掃、雑誌返品、廃棄登録が残っている深夜コンビニ。タクミが遠い目、エリは淡々。余韻のラスト。",
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

