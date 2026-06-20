# 第7話 画像カット台帳

対象: 第7話「宇宙宅配便、店留めです」

## 状態

- 全話先行準備として、シナリオ本文からCodex側の画像設計を作成。
- 画像生成はまだ実行しない。台本・音声・正式line ID確定後に開始する。
- `image_assignment_ep07.json` は正式line ID確定前の `ep07_v001-v100` 仮IDベース。

## 新キャラ / モチーフ設定案

- 銀色の宇宙宅配箱、銀河流通監査局通知、月面補給品。人物新キャラはなし。
- 中心業務/モチーフ: 宅配便受取・本人確認・宇宙再配送

## 画像生成時の注意点

- 画像内に字幕、会話ウィンドウ、時計、アプリUIを描かない。
- 9:16縦型。主要被写体は中央寄り。下部30〜40%は字幕UIセーフエリアとして重要物を置かない。
- 既存キャラは `character_visual_locks.json` 準拠。顔、髪型、制服、小道具、レジ外観を固定。
- レシートや端末の長文は読ませようとしない。必要ならHTML字幕/ログで表示する前提。
- 新モチーフは小さく扱い、急に巨大化させない。深夜コンビニの普通さとSF異常の同居を守る。

## 20カット採用計画

| cut | タイトル | 採用予定ファイル | 台本行ID範囲(仮) | 内容 |
|---:|---|---|---|---|
| 01 | 宅配端末が鳴る | `assets/scenes/planned/ep07_vc01_delivery_terminal_rings.png` | `ep07_v001-ep07_v005` | 午前二時十四分、宅配便端末が勝手に鳴る。配達予定なしなのにカウンター下に銀色の箱。 |
| 02 | 月面店留め箱 | `assets/scenes/planned/ep07_vc02_moon_pickup_box.png` | `ep07_v006-ep07_v010` | 銀色の宇宙宅配箱。月面基地店留めラベル風、シアンの配送ライン。文字は雰囲気。 |
| 03 | 受取番号から入る | `assets/scenes/planned/ep07_vc03_pickup_number_first.png` | `ep07_v011-ep07_v015` | ミナが受取番号を確認しようとする。タクミが月面よりそこかと驚く。 |
| 04 | 第十三レジ宇宙宅配確認 | `assets/scenes/planned/ep07_vc04_register_scans_space_delivery.png` | `ep07_v016-ep07_v020` | 二時十七分、第十三レジが宇宙宅配便を確認。現代日本コンビニへの誤配。 |
| 05 | 箱の中身 | `assets/scenes/planned/ep07_vc05_space_parcel_contents.png` | `ep07_v021-ep07_v025` | 無重力プリン、月面作業員用カップ麺、真空でも鳴る防犯ブザーが銀色箱に入っている。 |
| 06 | 無重力プリン跳ねる | `assets/scenes/planned/ep07_vc06_zero_g_pudding.png` | `ep07_v026-ep07_v030` | 無重力プリンが重力下で跳ねそうに揺れる。食べ物として致命的なコメディ。 |
| 07 | 汗田と銀河監査ラベル | `assets/scenes/planned/ep07_vc07_aseda_galactic_label.png` | `ep07_v031-ep07_v035` | 汗田がナビ端末で銀河流通監査局ラベルを読む。事務的な宇宙物流の気配。 |
| 08 | コピー機監査通知 | `assets/scenes/planned/ep07_vc08_galactic_audit_notice.png` | `ep07_v036-ep07_v040` | コピー機が銀河流通監査局通知を印刷。本人確認、重力差額、眠いBGMなどの事務的指摘。 |
| 09 | 座木山と月面地図 | `assets/scenes/planned/ep07_vc09_zakiyama_moon_map.png` | `ep07_v041-ep07_v045` | 座木山がコピー機に来て月面の道をツーリング目線で見る。釣り常連姿。 |
| 10 | 受取人確認 | `assets/scenes/planned/ep07_vc10_recipient_verification.png` | `ep07_v046-ep07_v050` | 第十三レジが月面店夜勤担当の本人確認を要求。受取人不在の端末画面。 |
| 11 | レシート本人確認候補 | `assets/scenes/planned/ep07_vc11_receipt_as_id.png` | `ep07_v051-ep07_v055` | クレーター作業許可証、銀河社員証、またはレシート、という本人確認候補の雰囲気。 |
| 12 | 危険署名一致 | `assets/scenes/planned/ep07_vc12_danger_signature_route.png` | `ep07_v056-ep07_v060` | 汗田が配送ログに未来青年の封印タグと同じ署名を見つける。 |
| 13 | 本人不在なら再配送 | `assets/scenes/planned/ep07_vc13_redelivery_decision.png` | `ep07_v061-ep07_v065` | ミナが本人がいないなら再配送と判断。宇宙にも再配送がある普通の業務感。 |
| 14 | 店留め保管料 | `assets/scenes/planned/ep07_vc14_storage_fee.png` | `ep07_v066-ep07_v070` | 第十三レジが店留め保管料を要求。タクミが宇宙からも取るのかと驚く。 |
| 15 | 再配送ラベル | `assets/scenes/planned/ep07_vc15_redelivery_label.png` | `ep07_v071-ep07_v075` | タクミが銀色箱に再配送ラベルを貼る。備考欄にこちらではプリンが跳ねます、の雰囲気。 |
| 16 | 銀河監査局へ通知 | `assets/scenes/planned/ep07_vc16_notify_galactic_audit.png` | `ep07_v076-ep07_v080` | 第十三レジが銀河流通監査局へ通知。シアンの通信ラインが箱から伸びる。 |
| 17 | 宇宙宅配便レシート | `assets/scenes/planned/ep07_vc17_space_delivery_receipt.png` | `ep07_v081-ep07_v085` | 宇宙宅配便再配送、無重力プリン未開封、危険知識署名一部一致のレシート。 |
| 18 | 月面地図を見る座木山 | `assets/scenes/planned/ep07_vc18_zakiyama_reads_moon_map.png` | `ep07_v086-ep07_v090` | 座木山がコピーされた月面地図を眺め、この道は夜暗そうと言う雰囲気。 |
| 19 | マニュアル店留め | `assets/scenes/planned/ep07_vc19_manual_space_pickup.png` | `ep07_v091-ep07_v095` | タクミが宇宙宅配便も受取番号が必要、月面でも店留めは店留めと書く。 |
| 20 | 地球の物流 | `assets/scenes/planned/ep07_vc20_earth_logistics_night.png` | `ep07_v096-ep07_v100` | 外の国道をトラックが通り過ぎ、地球の物流は普通に動く。深夜コンビニ外観。 |

## 保留事項

- Claudeの正式な台本行IDが出たら、assignmentsを正式IDに合わせる。
- 新キャラ/モチーフの見た目は、画像生成前に必要に応じてユーザー確認する。
