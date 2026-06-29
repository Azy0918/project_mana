# 第8話 画像カット台帳

対象: 第8話「月面店、発注しすぎました」

## 状態

- 全話先行準備として、シナリオ本文からCodex側の画像設計を作成。
- 画像生成はまだ実行しない。台本・音声・正式line ID確定後に開始する。
- `image_assignment_ep08.json` は正式line ID確定前の `ep08_v001-v100` 仮IDベース。

## 新キャラ / モチーフ設定案

- 月面店システムは画面内の無人店舗AIとして扱う。酸素グミ、銀河標準からあげ、真空対応ストローが主要モチーフ。
- 中心業務/モチーフ: 発注・棚割り・酸素グミ

## 画像生成時の注意点

- 画像内に字幕、会話ウィンドウ、時計、アプリUIを描かない。
- 9:16縦型。主要被写体は中央寄り。下部30〜40%は字幕UIセーフエリアとして重要物を置かない。
- 既存キャラは `character_visual_locks.json` 準拠。顔、髪型、制服、小道具、レジ外観を固定。
- レシートや端末の長文は読ませようとしない。必要ならHTML字幕/ログで表示する前提。
- 新モチーフは小さく扱い、急に巨大化させない。深夜コンビニの普通さとSF異常の同居を守る。

## 20カット採用計画

| cut | タイトル | 採用予定ファイル | 台本行ID範囲(仮) | 内容 |
|---:|---|---|---|---|
| 01 | 発注端末が震える | `assets/scenes/planned/ep08_vc01_order_terminal_shakes.png` | `ep08_v001-ep08_v005` | 午前二時十二分、発注端末が震え、酸素グミ一万個の異常発注を表示する。 |
| 02 | 酸素グミ一万個 | `assets/scenes/planned/ep08_vc02_oxygen_gummies_10000.png` | `ep08_v006-ep08_v010` | 発注端末画面と棚に入りきらない酸素グミのイメージ。タクミ困惑、エリは置けないと判断。 |
| 03 | 第十三レジ月面発注 | `assets/scenes/planned/ep08_vc03_register_moon_order.png` | `ep08_v011-ep08_v015` | 二時十七分、第十三レジが月面店発注データを確認。酸素グミ、銀河標準からあげ、真空ストロー。 |
| 04 | 補給線の計算 | `assets/scenes/planned/ep08_vc04_supply_line_calculation.png` | `ep08_v016-ep08_v020` | 汗田がナビ画面で月面基地の補給線を説明。食料品名目で酸素を分散配置する図。 |
| 05 | 危険知識一致率 | `assets/scenes/planned/ep08_vc05_dangerous_logistics_match.png` | `ep08_v021-ep08_v025` | 第十三レジが危険知識保持者の物流設計と一致率を表示。じわじわ上がる不穏さ。 |
| 06 | 三時間後納品警告 | `assets/scenes/planned/ep08_vc06_delivery_in_three_hours.png` | `ep08_v026-ep08_v030` | このままだと三時間後に酸素グミ一万個が現代店舗へ納品される警告。店内が埋まる想像。 |
| 07 | 三列まで | `assets/scenes/planned/ep08_vc07_three_rows_limit.png` | `ep08_v031-ep08_v035` | エリが売場を見て三列までと判断。棚割りで宇宙補給を止める。 |
| 08 | 棚が安全装置 | `assets/scenes/planned/ep08_vc08_shelf_as_safety.png` | `ep08_v036-ep08_v040` | 汗田が店舗に置ける量を上限条件にすれば暴走しないと納得。棚とナビの対比。 |
| 09 | 唐沢発注確認 | `assets/scenes/planned/ep08_vc09_karasawa_order_check.png` | `ep08_v041-ep08_v045` | 唐沢が深夜発注を確認しに来店。酸素グミ一万個を発注過多と冷静に判断。 |
| 10 | 現実の数字で宇宙を殴る | `assets/scenes/planned/ep08_vc10_real_numbers_vs_space.png` | `ep08_v046-ep08_v050` | 唐沢が三列展開なら最大二十四個と現実の数字で補正。タクミが驚く。 |
| 11 | 二十四個へ補正 | `assets/scenes/planned/ep08_vc11_order_corrected_24.png` | `ep08_v051-ep08_v055` | 第十三レジが棚割り上限を受理し、発注数を二十四個へ補正。 |
| 12 | 月面店通信 | `assets/scenes/planned/ep08_vc12_moon_store_call.png` | `ep08_v056-ep08_v060` | 無人の月面店内が画面に映る。棚の端で酸素グミのキャラクターが不安げに揺れる。 |
| 13 | 一万個ないと不安 | `assets/scenes/planned/ep08_vc13_moon_store_anxiety.png` | `ep08_v061-ep08_v065` | 月面店システムが一万個ないと不安と訴える。エリは三列まで。 |
| 14 | 不安と在庫 | `assets/scenes/planned/ep08_vc14_anxiety_inventory.png` | `ep08_v066-ep08_v070` | 汗田が不安を在庫で埋めると物流が暴走すると語る。酸素グミの山が薄く消えていく。 |
| 15 | 仮発注確定 | `assets/scenes/planned/ep08_vc15_provisional_order_confirm.png` | `ep08_v071-ep08_v075` | エリが二十四個の仮発注を確定。端末の警告が落ち着く。 |
| 16 | 月面店発注レシート | `assets/scenes/planned/ep08_vc16_moon_order_receipt.png` | `ep08_v076-ep08_v080` | 月面店発注補正、酸素グミ一万個から二十四個、棚割り三列までのレシート。 |
| 17 | 唐沢の特殊レジ施策 | `assets/scenes/planned/ep08_vc17_karasawa_special_register.png` | `ep08_v081-ep08_v085` | 唐沢が特殊レジ施策として回転率まで指摘。時空処理中の第十三レジ。 |
| 18 | マニュアル棚割り | `assets/scenes/planned/ep08_vc18_manual_shelf_limit.png` | `ep08_v086-ep08_v090` | タクミが置けないものは売れない、発注数は不安で決めないと書く。 |
| 19 | 酸素グミ空気味 | `assets/scenes/planned/ep08_vc19_oxygen_gummy_air_flavor.png` | `ep08_v091-ep08_v095` | エリが酸素グミの味を聞き、第十三レジが空気味と示す。酸素グミの小袋。 |
| 20 | 棚は普通に三列 | `assets/scenes/planned/ep08_vc20_shelf_three_rows_normal.png` | `ep08_v096-ep08_v100` | 売場棚に酸素グミが三列だけ並ぶ。月面規模の問題が普通の棚割りに収まる。 |

## 保留事項

- Claudeの正式な台本行IDが出たら、assignmentsを正式IDに合わせる。
- 新キャラ/モチーフの見た目は、画像生成前に必要に応じてユーザー確認する。
