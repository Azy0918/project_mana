# 第5話 画像カット台帳

対象: 第5話「昭和の伝票、まだ未処理です」

## 状態

- 全話先行準備として、シナリオ本文からCodex側の画像設計を作成。
- 画像生成はまだ実行しない。台本・音声・正式line ID確定後に開始する。
- `image_assignment_ep05.json` は正式line ID確定前の `ep05_v001-v100` 仮IDベース。

## 新キャラ / モチーフ設定案

- 新キャラなし。昭和伝票、保留ハンコ、テプラ、伝票ファイルが主要モチーフ。
- 中心業務/モチーフ: 伝票整理・昭和伝票・記憶封印ログ

## 画像生成時の注意点

- 画像内に字幕、会話ウィンドウ、時計、アプリUIを描かない。
- 9:16縦型。主要被写体は中央寄り。下部30〜40%は字幕UIセーフエリアとして重要物を置かない。
- 既存キャラは `character_visual_locks.json` 準拠。顔、髪型、制服、小道具、レジ外観を固定。
- レシートや端末の長文は読ませようとしない。必要ならHTML字幕/ログで表示する前提。
- 新モチーフは小さく扱い、急に巨大化させない。深夜コンビニの普通さとSF異常の同居を守る。

## 20カット採用計画

| cut | タイトル | 採用予定ファイル | 台本行ID範囲(仮) | 内容 |
|---:|---|---|---|---|
| 01 | 古い紙束が落ちる | `assets/scenes/planned/ep05_vc01_old_slips_fall.png` | `ep05_v001-ep05_v005` | バックヤードの棚から黄ばんだ手書き伝票の束が落ちる。タクミが拾い、エリが未処理か見る。 |
| 02 | 昭和五十八年伝票 | `assets/scenes/planned/ep05_vc02_showa_58_slips.png` | `ep05_v006-ep05_v010` | 牛乳、食パン、乾電池、謎のり弁などが並ぶ古い商店伝票。紙の黄ばみと手書き感、文字は雰囲気重視。 |
| 03 | 伝票は諦めない | `assets/scenes/planned/ep05_vc03_slips_do_not_give_up.png` | `ep05_v011-ep05_v015` | エリが淡々と伝票整理の姿勢を見せ、タクミが昭和から未処理なら諦めたい顔。 |
| 04 | 第十三レジ読み込み | `assets/scenes/planned/ep05_vc04_register_scans_old_slips.png` | `ep05_v016-ep05_v020` | 二時十七分、第十三レジが現れ、古い伝票を一枚ずつ読み込む。紙がレジへ吸い込まれる。 |
| 05 | 未来記録混入 | `assets/scenes/planned/ep05_vc05_future_log_in_slip.png` | `ep05_v021-ep05_v025` | 伝票表示に記憶返品タグ、危険知識封印、開封厳禁の異質な記録が混ざる。 |
| 06 | 汗田と古紙警告 | `assets/scenes/planned/ep05_vc06_aseda_old_paper_warning.png` | `ep05_v026-ep05_v030` | 汗田がナビに呼ばれて来店。ナビに古紙の匂いが危険という警告風表示。 |
| 07 | 銀色線入り伝票 | `assets/scenes/planned/ep05_vc07_silver_fiber_slip.png` | `ep05_v031-ep05_v035` | 汗田が伝票を光に透かし、紙の繊維に細い銀色の線を見つける。 |
| 08 | 商店伝票に偽装 | `assets/scenes/planned/ep05_vc08_disguised_future_log.png` | `ep05_v036-ep05_v040` | 未来青年の記憶封印ログが古い商店伝票に偽装されている様子を、紙束と微細回路の対比で表現。 |
| 09 | 仕分け作業 | `assets/scenes/planned/ep05_vc09_sorting_slips.png` | `ep05_v041-ep05_v045` | 牛乳、食パン、乾電池、記憶封印、のり弁、危険知識などを机に並べて地味に仕分ける。 |
| 10 | 分類精度六十八 | `assets/scenes/planned/ep05_vc10_classification_low.png` | `ep05_v046-ep05_v050` | 第十三レジが分類精度低めを表示。タクミが低いと驚く。 |
| 11 | 座木山の店の記憶 | `assets/scenes/planned/ep05_vc11_zakiyama_old_store_memory.png` | `ep05_v051-ep05_v055` | 座木山が昔ここに小さい雑貨屋があったと語る。夜釣り常連姿、古い場所の記憶。 |
| 12 | 夜の人を助けた場所 | `assets/scenes/planned/ep05_vc12_old_store_helped_night_people.png` | `ep05_v056-ep05_v060` | 昔の小さな雑貨屋の幻影と現在のコンビニが重なる。電池を買う夜の人の記憶を静かに表現。 |
| 13 | 判断できないものは預かる | `assets/scenes/planned/ep05_vc13_hold_if_undecidable.png` | `ep05_v061-ep05_v065` | 問題の伝票に手書きで判断できないものは預かる、というメモ。長文は読ませず印象で。 |
| 14 | 処理選択三択 | `assets/scenes/planned/ep05_vc14_processing_choices_slips.png` | `ep05_v066-ep05_v070` | 第十三レジが過去伝票廃棄、未来記録開封、現代店舗保留を提示する。 |
| 15 | 保留ハンコ | `assets/scenes/planned/ep05_vc15_pending_stamp.png` | `ep05_v071-ep05_v075` | エリが伝票へ保留ハンコを押す。危険知識を剥がさない判断。 |
| 16 | 未処理から保留へ | `assets/scenes/planned/ep05_vc16_from_unprocessed_to_pending.png` | `ep05_v076-ep05_v080` | 第十三レジが過去伝票を未処理から保留へ移行。紙束の光が落ち着く。 |
| 17 | 昭和伝票レシート | `assets/scenes/planned/ep05_vc17_showa_slip_receipt.png` | `ep05_v081-ep05_v085` | 昭和伝票整理済み、記憶返品タグ保留、店長確認未了などのレシート。 |
| 18 | テプラ出す | `assets/scenes/planned/ep05_vc18_label_maker.png` | `ep05_v086-ep05_v090` | エリが文具箱からテプラを出す。世界を救う前にラベル作り。 |
| 19 | 伝票ファイル保管 | `assets/scenes/planned/ep05_vc19_slip_file_storage.png` | `ep05_v091-ep05_v095` | 背表紙を付けた伝票ファイルに保留伝票を入れる。バックヤードの棚へ。 |
| 20 | マニュアル伝票整理 | `assets/scenes/planned/ep05_vc20_manual_slip_note.png` | `ep05_v096-ep05_v100` | タクミが危険知識は剥がさない、古い伝票でも未処理なら処理するとマニュアルに書く。 |

## 保留事項

- Claudeの正式な台本行IDが出たら、assignmentsを正式IDに合わせる。
- 新キャラ/モチーフの見た目は、画像生成前に必要に応じてユーザー確認する。
