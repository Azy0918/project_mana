# 第10話 画像カット台帳

対象: 第10話「あの会社員、返品済みです」

## 状態

- 全話先行準備として、シナリオ本文からCodex側の画像設計を作成。
- 画像生成はまだ実行しない。台本・音声・正式line ID確定後に開始する。
- `image_assignment_ep10.json` は正式line ID確定前の `ep10_v001-v100` 仮IDベース。

## 新キャラ / モチーフ設定案

- 未来青年の第10話姿: 普通のジャケット姿だが第1話と同一人物。character_visual_locksのfuture_worker_ep01を使用。
- 中心業務/モチーフ: 本人確認・レシート確認・未来青年再来店

## 画像生成時の注意点

- 画像内に字幕、会話ウィンドウ、時計、アプリUIを描かない。
- 9:16縦型。主要被写体は中央寄り。下部30〜40%は字幕UIセーフエリアとして重要物を置かない。
- 既存キャラは `character_visual_locks.json` 準拠。顔、髪型、制服、小道具、レジ外観を固定。
- レシートや端末の長文は読ませようとしない。必要ならHTML字幕/ログで表示する前提。
- 新モチーフは小さく扱い、急に巨大化させない。深夜コンビニの普通さとSF異常の同居を守る。

## 20カット採用計画

| cut | タイトル | 採用予定ファイル | 台本行ID範囲(仮) | 内容 |
|---:|---|---|---|---|
| 01 | 第1話レシート確認 | `assets/scenes/planned/ep10_vc01_ep1_receipt_file.png` | `ep10_v001-ep10_v005` | 午前二時十一分、タクミがバックヤードで第1話の時空返品レシートファイルを開く。 |
| 02 | 人間にレシート | `assets/scenes/planned/ep10_vc02_receipt_for_person.png` | `ep10_v006-ep10_v010` | エリが本人確認にレシートを使う前提で準備し、タクミが人間に使う言葉ではないと困惑。 |
| 03 | 未来青年再来店 | `assets/scenes/planned/ep10_vc03_future_worker_returns.png` | `ep10_v011-ep10_v015` | 自動ドアから普通のジャケット姿の未来青年が入ってくる。顔は第1話本人、疲れた目と首元パッチ。 |
| 04 | 前にも来ましたか | `assets/scenes/planned/ep10_vc04_have_i_been_here.png` | `ep10_v016-ep10_v020` | 青年がここに前にも来たかと不安げに尋ねる。タクミが未来おにぎりを思い出す。 |
| 05 | 劣化する記憶タグ | `assets/scenes/planned/ep10_vc05_deteriorating_memory_tag.png` | `ep10_v021-ep10_v025` | 未来青年の首元の透明パッチが端から浮き、銀色回路が弱く点滅する。 |
| 06 | 第十三レジ危険知識確認 | `assets/scenes/planned/ep10_vc06_register_danger_holder.png` | `ep10_v026-ep10_v030` | 二時十七分、第十三レジが危険知識保持者、記憶返品タグ劣化、未来大戦争発生率上昇を確認。 |
| 07 | 外見年齢と残業 | `assets/scenes/planned/ep10_vc07_age_and_overtime.png` | `ep10_v031-ep10_v035` | 第十三レジが外見年齢と残業原因を示し、タクミがレジにツッコむ。 |
| 08 | 汗田の赤いナビ | `assets/scenes/planned/ep10_vc08_aseda_red_nav.png` | `ep10_v036-ep10_v040` | 汗田が赤く点滅するナビ端末を持って来店。封印タグが剥がれかけていると説明。 |
| 09 | ただの会社員です | `assets/scenes/planned/ep10_vc09_just_office_worker.png` | `ep10_v041-ep10_v045` | 青年がただの会社員ですと不安そうに首元を押さえる。 |
| 10 | エリがレシート確認 | `assets/scenes/planned/ep10_vc10_mina_receipt_check.png` | `ep10_v046-ep10_v050` | エリが第1話レシートを出してお客様確認を始める。 |
| 11 | バーコード照合 | `assets/scenes/planned/ep10_vc11_barcode_verification.png` | `ep10_v051-ep10_v055` | タクミがレシートのバーコードを読み取る。第十三レジが本人確認一部完了を示す。 |
| 12 | 返品済み青年 | `assets/scenes/planned/ep10_vc12_returned_youth.png` | `ep10_v056-ep10_v060` | 青年が私、返品済みなんですかとレシートを見る。タクミが言い方がひどいだけとフォロー。 |
| 13 | 剥がさない方がいい | `assets/scenes/planned/ep10_vc13_do_not_peel_tag.png` | `ep10_v061-ep10_v065` | エリが首元パッチを見て剥がさない方がいいと言う。青年が従う。 |
| 14 | 処理候補四択 | `assets/scenes/planned/ep10_vc14_future_worker_choices.png` | `ep10_v066-ep10_v070` | 第十三レジが未来へ返品、記憶開封、宇宙監査局返送、現代店舗一時保留を提示。 |
| 15 | 汗田がまだ決めるな | `assets/scenes/planned/ep10_vc15_aseda_do_not_decide.png` | `ep10_v071-ep10_v075` | 汗田が本人の記憶と知識の価値と危険性を整理できていないと止める。 |
| 16 | 一時保留受理 | `assets/scenes/planned/ep10_vc16_temporary_hold.png` | `ep10_v076-ep10_v080` | エリが保留を選び、第十三レジが一時保留を受理。次回棚卸し時に再確認。 |
| 17 | コーヒー飲みます | `assets/scenes/planned/ep10_vc17_coffee_for_worker.png` | `ep10_v081-ep10_v085` | タクミが未来青年にコーヒーを勧める。青年が少し笑いレギュラーを選ぶ。 |
| 18 | 本人確認レシート | `assets/scenes/planned/ep10_vc18_identity_receipt.png` | `ep10_v086-ep10_v090` | 未来青年本人確認、記憶返品タグ劣化、現代店舗一時保留、ホットコーヒー一件のレシート。 |
| 19 | イートインの青年 | `assets/scenes/planned/ep10_vc19_worker_at_eatin.png` | `ep10_v091-ep10_v095` | 青年がコーヒーを持ってイートインの端に座る。普通の客のようで普通ではない。 |
| 20 | 第十二第十四予告 | `assets/scenes/planned/ep10_vc20_copy_registers_forecast.png` | `ep10_v096-ep10_v100` | コピー機が明日、第十二レジと第十四レジの記録が混ざると予告紙を出す。 |

## 保留事項

- Claudeの正式な台本行IDが出たら、assignmentsを正式IDに合わせる。
- 新キャラ/モチーフの見た目は、画像生成前に必要に応じてユーザー確認する。
