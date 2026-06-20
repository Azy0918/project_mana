# 第9話 画像カット台帳

対象: 第9話「銀河ポイントカードはお持ちですか？」

## 状態

- 全話先行準備として、シナリオ本文からCodex側の画像設計を作成。
- 画像生成はまだ実行しない。台本・音声・正式line ID確定後に開始する。
- `image_assignment_ep09.json` は正式line ID確定前の `ep09_v001-v100` 仮IDベース。

## 新キャラ / モチーフ設定案

- 銀河共通ポイントカード、八兆ポイント、二億年前の最終利用日が主要モチーフ。
- 中心業務/モチーフ: ポイント処理・銀河共通ポイント・再来店予告

## 画像生成時の注意点

- 画像内に字幕、会話ウィンドウ、時計、アプリUIを描かない。
- 9:16縦型。主要被写体は中央寄り。下部30〜40%は字幕UIセーフエリアとして重要物を置かない。
- 既存キャラは `character_visual_locks.json` 準拠。顔、髪型、制服、小道具、レジ外観を固定。
- レシートや端末の長文は読ませようとしない。必要ならHTML字幕/ログで表示する前提。
- 新モチーフは小さく扱い、急に巨大化させない。深夜コンビニの普通さとSF異常の同居を守る。

## 20カット採用計画

| cut | タイトル | 採用予定ファイル | 台本行ID範囲(仮) | 内容 |
|---:|---|---|---|---|
| 01 | 星空ポイント端末 | `assets/scenes/planned/ep09_vc01_starry_point_reader.png` | `ep09_v001-ep09_v005` | 午前二時六分、レジ横のポイントカード読取機が星空のように光る。 |
| 02 | 座木山がカードを落とす | `assets/scenes/planned/ep09_vc02_zakiyama_drops_card.png` | `ep09_v006-ep09_v010` | 座木山がコピー機へ向かう途中で古いカードを落とす。夜釣り常連姿、タクミが拾う。 |
| 03 | 銀河共通ポイントカード | `assets/scenes/planned/ep09_vc03_galactic_point_card.png` | `ep09_v011-ep09_v015` | 古いカードに銀河共通ポイントの雰囲気。星屑のようなホログラム、長文は読ませない。 |
| 04 | 第十三レジ八兆ポイント | `assets/scenes/planned/ep09_vc04_register_eight_trillion.png` | `ep09_v016-ep09_v020` | 二時十七分、第十三レジが八兆ポイント残高を確認。タクミの手が震える。 |
| 05 | 地球円変換禁止 | `assets/scenes/planned/ep09_vc05_no_currency_conversion.png` | `ep09_v021-ep09_v025` | 第十三レジが地球円変換を提案し、タクミが全力で止める。 |
| 06 | 店が国になる | `assets/scenes/planned/ep09_vc06_store_becomes_country.png` | `ep09_v026-ep09_v030` | ミナが使えるなら使うかと傾げ、タクミが店が国になると焦る。ポイント光が店内を包む。 |
| 07 | 宇宙物流信用残高 | `assets/scenes/planned/ep09_vc07_cosmic_credit_balance.png` | `ep09_v031-ep09_v035` | 汗田がナビで宇宙物流の信用残高だと説明。変換すると補給権限が集まる不穏な図。 |
| 08 | 再来店予定通知 | `assets/scenes/planned/ep09_vc08_future_worker_return_notice.png` | `ep09_v036-ep09_v040` | 第十三レジが危険知識保持者の再来店予定を通知。未来青年の首元タグを思わせる小さな記号。 |
| 09 | 唐沢客単価確認 | `assets/scenes/planned/ep09_vc09_karasawa_high_unit_price.png` | `ep09_v041-ep09_v045` | 唐沢が深夜二時台の客単価が高いと来店。タクミが上がる寸前ですと青ざめる。 |
| 10 | 異常値は保留 | `assets/scenes/planned/ep09_vc10_abnormal_value_hold.png` | `ep09_v046-ep09_v050` | 唐沢が八兆ポイントを会計に乗せず集計前に保留と判断。 |
| 11 | 処理候補四択 | `assets/scenes/planned/ep09_vc11_point_processing_choices.png` | `ep09_v051-ep09_v055` | 第十三レジが地球円変換、銀河残高維持、期限切れ処理、保留を提示。 |
| 12 | 座木山は使わない | `assets/scenes/planned/ep09_vc12_zakiyama_refuses_points.png` | `ep09_v056-ep09_v060` | 座木山が貯めた覚えのないものは使うとあとが怖いと核心を言う。 |
| 13 | 最終利用日二億年前 | `assets/scenes/planned/ep09_vc13_last_used_200_million.png` | `ep09_v061-ep09_v065` | 第十三レジが最終利用日二億年前を示す。タクミが長期未利用すぎると驚く。 |
| 14 | 唐沢の失効処理 | `assets/scenes/planned/ep09_vc14_karasawa_expiration.png` | `ep09_v066-ep09_v070` | 唐沢が即答で失効処理を指示。現実のポイント運用が宇宙に勝つ。 |
| 15 | 銀河ポイント失効 | `assets/scenes/planned/ep09_vc15_galactic_points_expire.png` | `ep09_v071-ep09_v075` | 蛍光灯が星空のように瞬き、残高が八兆からゼロへ減っていく光景。 |
| 16 | 店売上正常範囲 | `assets/scenes/planned/ep09_vc16_sales_normal_range.png` | `ep09_v076-ep09_v080` | 第十三レジが失効完了、店の売上正常範囲を示し、タクミが胸をなで下ろす。 |
| 17 | 銀河ポイントレシート | `assets/scenes/planned/ep09_vc17_galactic_point_receipt.png` | `ep09_v081-ep09_v085` | 銀河共通ポイント八兆、地球円変換未実施、危険知識保持者再来店予定のレシート。 |
| 18 | 未来青年が来る | `assets/scenes/planned/ep09_vc18_future_worker_coming.png` | `ep09_v086-ep09_v090` | タクミと汗田がレシート末尾を見て、未来青年が来ることを認識。 |
| 19 | レシート探しておこう | `assets/scenes/planned/ep09_vc19_prepare_receipts.png` | `ep09_v091-ep09_v095` | ミナが本人確認用のレシートを探しておこうと淡々。タクミが人間確認の準備に困惑。 |
| 20 | コピー機の予告 | `assets/scenes/planned/ep09_vc20_copy_predicts_returned_person.png` | `ep09_v096-ep09_v100` | コピー機が明日、返品済みの人が来ます、と予告紙を出す。タクミがため息。 |

## 保留事項

- Claudeの正式な台本行IDが出たら、assignmentsを正式IDに合わせる。
- 新キャラ/モチーフの見た目は、画像生成前に必要に応じてユーザー確認する。
