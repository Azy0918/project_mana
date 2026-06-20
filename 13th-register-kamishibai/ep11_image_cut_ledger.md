# 第11話 画像カット台帳

対象: 第11話「第十二レジと第十四レジ」

## 状態

- 全話先行準備として、シナリオ本文からCodex側の画像設計を作成。
- 画像生成はまだ実行しない。台本・音声・正式line ID確定後に開始する。
- `image_assignment_ep11.json` は正式line ID確定前の `ep11_v001-v100` 仮IDベース。

## 新キャラ / モチーフ設定案

- 第十二レジ、第十四レジをキャラ固定に追加済み。未来青年も現物確認対象として登場。
- 中心業務/モチーフ: 棚卸し・第十二レジ・第十四レジ・現物確認

## 画像生成時の注意点

- 画像内に字幕、会話ウィンドウ、時計、アプリUIを描かない。
- 9:16縦型。主要被写体は中央寄り。下部30〜40%は字幕UIセーフエリアとして重要物を置かない。
- 既存キャラは `character_visual_locks.json` 準拠。顔、髪型、制服、小道具、レジ外観を固定。
- レシートや端末の長文は読ませようとしない。必要ならHTML字幕/ログで表示する前提。
- 新モチーフは小さく扱い、急に巨大化させない。深夜コンビニの普通さとSF異常の同居を守る。

## 20カット採用計画

| cut | タイトル | 採用予定ファイル | 台本行ID範囲(仮) | 内容 |
|---:|---|---|---|---|
| 01 | 棚卸し表に人間 | `assets/scenes/planned/ep11_vc01_inventory_human.png` | `ep11_v001-ep11_v005` | 午前二時二分、棚卸し表に危険知識保持者一名が入っていてタクミが困惑。 |
| 02 | 保留中の未来青年 | `assets/scenes/planned/ep11_vc02_held_future_worker_eatin.png` | `ep11_v006-ep11_v010` | 未来青年がイートイン端でコーヒーを持ち困った顔。保留中だから在庫扱いされるコメディ。 |
| 03 | 三台のレジ影 | `assets/scenes/planned/ep11_vc03_three_register_shadows.png` | `ep11_v011-ep11_v015` | 二時十七分、第十三レジの左右に二台の影が揺れる。古いレジと透明未来レジの気配。 |
| 04 | 第十二レジ出現 | `assets/scenes/planned/ep11_vc04_twelfth_register_appears.png` | `ep11_v016-ep11_v020` | 左に古い木目調の第十二レジが現れ、過去処理を優先すると示す。 |
| 05 | 第十四レジ出現 | `assets/scenes/planned/ep11_vc05_fourteenth_register_appears.png` | `ep11_v021-ep11_v025` | 右に透明な未来型の第十四レジが現れ、未来処理を優先すると示す。 |
| 06 | 過去へ返品と未来へ返送 | `assets/scenes/planned/ep11_vc06_past_future_demands.png` | `ep11_v026-ep11_v030` | 第十二レジは過去へ返品、第十四レジは未来へ返送を要求し、未来青年が青ざめる。 |
| 07 | 汗田は人間を見る | `assets/scenes/planned/ep11_vc07_aseda_human_first.png` | `ep11_v031-ep11_v035` | 汗田がナビを置き、今ここにいる人間を無視していると指摘。 |
| 08 | 第十三レジは今を処理 | `assets/scenes/planned/ep11_vc08_thirteenth_process_now.png` | `ep11_v036-ep11_v040` | 第十三レジが今の業務を処理すると示す。三台のレジの思想対比。 |
| 09 | ミナは数えよう | `assets/scenes/planned/ep11_vc09_mina_count_inventory.png` | `ep11_v041-ep11_v045` | ミナが棚卸し表を持ち、今あるものを数えようと言う。タクミが驚く。 |
| 10 | 過去の商品表示 | `assets/scenes/planned/ep11_vc10_past_items_display.png` | `ep11_v046-ep11_v050` | 第十二レジが昭和伝票、未成立パン、昨日バニラなど過去の商品を表示。 |
| 11 | 未来の商品表示 | `assets/scenes/planned/ep11_vc11_future_items_display.png` | `ep11_v051-ep11_v055` | 第十四レジが酸素グミ、銀河ポイント、物流大戦争発生確率など未来の商品を表示。 |
| 12 | 現物だけ | `assets/scenes/planned/ep11_vc12_actual_items_only.png` | `ep11_v056-ep11_v060` | ミナが現物だけと言い、タクミが実際にあるものだけを数える準備。 |
| 13 | 店内を走る棚卸し | `assets/scenes/planned/ep11_vc13_takumi_runs_inventory.png` | `ep11_v061-ep11_v065` | タクミが店内を走り、保留箱のパン、明日ミルク、レシートファイル、未来青年本人を確認。 |
| 14 | 過去未来と不一致 | `assets/scenes/planned/ep11_vc14_past_future_mismatch.png` | `ep11_v066-ep11_v070` | 第十二レジと第十四レジがそれぞれ不一致を示し、現物確認と対立する。 |
| 15 | 今の店ではこれだけ | `assets/scenes/planned/ep11_vc15_current_store_stamp.png` | `ep11_v071-ep11_v075` | ミナが棚卸し表にハンコを押す。今の店ではこれだけ、という確定感。 |
| 16 | 左右レジ保留へ | `assets/scenes/planned/ep11_vc16_side_registers_hold.png` | `ep11_v076-ep11_v080` | 第十三レジが第十二・第十四レジの記録を保留へ移行し、左右のレジが薄くなる。 |
| 17 | 今、処理中です | `assets/scenes/planned/ep11_vc17_now_processing.png` | `ep11_v081-ep11_v085` | 第十三レジが今、処理中ですと示す。タクミが意味に気づく。 |
| 18 | 唐沢の現金過不足 | `assets/scenes/planned/ep11_vc18_karasawa_cash_difference.png` | `ep11_v086-ep11_v090` | 唐沢が巡回に来て、数字が合わないものは保留、現金過不足は出さないと言う。 |
| 19 | 三レジ棚卸しレシート | `assets/scenes/planned/ep11_vc19_three_register_receipt.png` | `ep11_v091-ep11_v095` | 第十二レジ記録保留、第十四レジ記録保留、未来大戦争未確定、唐沢指摘有効のレシート。 |
| 20 | 全部の伝票予告 | `assets/scenes/planned/ep11_vc20_all_slips_forecast.png` | `ep11_v096-ep11_v100` | コピー機が明日、全部の伝票が来ます、と紙を吐き出す。第十三レジだけが残る。 |

## 保留事項

- Claudeの正式な台本行IDが出たら、assignmentsを正式IDに合わせる。
- 新キャラ/モチーフの見た目は、画像生成前に必要に応じてユーザー確認する。
