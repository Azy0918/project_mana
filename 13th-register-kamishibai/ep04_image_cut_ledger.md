# 第4話 画像カット台帳

対象: 第4話「未来レシートは先に謝る」

## 状態

- 全話先行準備として、シナリオ本文からCodex側の画像設計を作成。
- 画像生成はまだ実行しない。台本・音声・正式line ID確定後に開始する。
- `image_assignment_ep04.json` は正式line ID確定前の `ep04_v001-v100` 仮IDベース。

## 新キャラ / モチーフ設定案

- 単発: 眠そうなトラック運転手。キャラロック追加はせず、深夜客として各プロンプト内で指定。
- 中心業務/モチーフ: コピー機・未来クレーム・唐揚げ棒・未使用謝罪

## 画像生成時の注意点

- 画像内に字幕、会話ウィンドウ、時計、アプリUIを描かない。
- 9:16縦型。主要被写体は中央寄り。下部30〜40%は字幕UIセーフエリアとして重要物を置かない。
- 既存キャラは `character_visual_locks.json` 準拠。顔、髪型、制服、小道具、レジ外観を固定。
- レシートや端末の長文は読ませようとしない。必要ならHTML字幕/ログで表示する前提。
- 新モチーフは小さく扱い、急に巨大化させない。深夜コンビニの普通さとSF異常の同居を守る。

## 20カット採用計画

| cut | タイトル | 採用予定ファイル | 台本行ID範囲(仮) | 内容 |
|---:|---|---|---|---|
| 01 | コピー機が勝手に起動 | `assets/scenes/planned/ep04_vc01_copy_machine_starts.png` | `ep04_v001-ep04_v005` | 午前二時五分、深夜コンビニのコピー機が誰も触っていないのに起動する。タクミが床清掃機を止め、エリが淡々と見る。 |
| 02 | 未来クレーム予告紙 | `assets/scenes/planned/ep04_vc02_future_complaint_print.png` | `ep04_v006-ep04_v010` | コピー機から未来クレーム予告の紙が出る。唐揚げ棒のお客様が怒る予告を、長文は読ませずレシート風の不穏な紙として見せる。 |
| 03 | ホットスナック確認 | `assets/scenes/planned/ep04_vc03_hot_snack_case.png` | `ep04_v011-ep04_v015` | エリがホットスナックケースを見る。唐揚げ棒が温かい光の中にあり、タクミが意味不明な予告に困惑する。 |
| 04 | 座木山コピー来店 | `assets/scenes/planned/ep04_vc04_zakiyama_copy_visit.png` | `ep04_v016-ep04_v020` | 座木山辰哉が夜釣り帰りの装備でコピー機へ向かう。未来クレーム紙とコピー機、タクミのツッコミ。 |
| 05 | 先に謝ればいい | `assets/scenes/planned/ep04_vc05_pre_apology_notice.png` | `ep04_v021-ep04_v025` | エリがコピー機横に謝罪メモ風の紙を貼る。発生前クレームへ先に謝るシュールな接客準備。 |
| 06 | 第十三レジ出現 | `assets/scenes/planned/ep04_vc06_register_appears_complaint.png` | `ep04_v026-ep04_v030` | 二時十七分、第十三レジが現れ、唐揚げ棒の温度と思い出の温度不一致を警告する。 |
| 07 | 汗田のログ解析 | `assets/scenes/planned/ep04_vc07_aseda_log_analysis.png` | `ep04_v031-ep04_v035` | 汗田がナビ端末を見ながら未来クレーム処理ログを解析する。謝罪だけでは因果固定の恐れ。 |
| 08 | 謝る唐揚げ棒 | `assets/scenes/planned/ep04_vc08_karaage_pre_apology.png` | `ep04_v036-ep04_v040` | ホットスナックケース内で唐揚げ棒が小さく震え、紙旗でまだ怒られていない雰囲気を出す。商品が先に謝るコメディ。 |
| 09 | 未来本部マニュアル | `assets/scenes/planned/ep04_vc09_future_manual_basic_greeting.png` | `ep04_v041-ep04_v045` | 第十三レジ画面に未来本部マニュアル風の表示。まず挨拶、という普通すぎる対応を強調。 |
| 10 | トラック運転手来店 | `assets/scenes/planned/ep04_vc10_truck_driver_enters.png` | `ep04_v046-ep04_v050` | 二時二十八分、眠そうな中年トラック運転手が入店し、唐揚げ棒を注文する。単発客、作業着、疲れたが悪人ではない。 |
| 11 | 気持ちは熱めです | `assets/scenes/planned/ep04_vc11_takumi_serves_karaage.png` | `ep04_v051-ep04_v055` | タクミが緊張しながら唐揚げ棒を渡す。ホットスナックケース、レジカウンター、未来クレーム紙。 |
| 12 | 思い出の温度一致 | `assets/scenes/planned/ep04_vc12_memory_temperature_matches.png` | `ep04_v056-ep04_v060` | 運転手が唐揚げ棒を食べて昔の夜中を思い出す。怒らず少し懐かしい表情、タクミが紙を見る。 |
| 13 | コピー機静まる | `assets/scenes/planned/ep04_vc13_copy_machine_satisfied.png` | `ep04_v061-ep04_v065` | コピー機が満足そうに静かになる。店内は普通の夜勤へ戻りかけ、第十三レジだけが処理を続ける。 |
| 14 | 未使用謝罪の在庫 | `assets/scenes/planned/ep04_vc14_unused_apology_inventory.png` | `ep04_v066-ep04_v070` | 第十三レジが未使用謝罪一件を示す。エリが取っておくか聞き、タクミが返品を望む。 |
| 15 | 未使用謝罪を時空返品 | `assets/scenes/planned/ep04_vc15_apology_time_return.png` | `ep04_v071-ep04_v075` | 未使用謝罪がレシート状の光として第十三レジに吸い込まれる。静かなSF処理。 |
| 16 | 未来クレームレシート | `assets/scenes/planned/ep04_vc16_complaint_receipt.png` | `ep04_v076-ep04_v080` | 第十三レジからレシートが出る。未来クレーム回避、唐揚げ棒販売完了、返品済み青年の確認不能を匂わせる。 |
| 17 | 返品済み青年の影 | `assets/scenes/planned/ep04_vc17_future_worker_hint.png` | `ep04_v081-ep04_v085` | タクミと汗田がレシート末尾を見て沈黙する。第1話の未来青年を思わせる透明タグの小さな記号。 |
| 18 | 座木山の白黒地図 | `assets/scenes/planned/ep04_vc18_zakiyama_blackwhite_map.png` | `ep04_v086-ep04_v090` | 座木山がコピー機から白黒の地図を取り出す。色がつくと思い出しすぎる、という余韻。 |
| 19 | マニュアル追記 | `assets/scenes/planned/ep04_vc19_manual_complaint_note.png` | `ep04_v091-ep04_v095` | タクミがマニュアルにコピー機の予告は半分だけ信じると書く。唐揚げ棒は普通に売る。 |
| 20 | 通常営業へ戻る | `assets/scenes/planned/ep04_vc20_night_shift_after_complaint.png` | `ep04_v096-ep04_v100` | ホットスナックケースとコピー機、深夜コンビニの静かな通常営業。次の異常の気配だけ残す。 |

## 保留事項

- Claudeの正式な台本行IDが出たら、assignmentsを正式IDに合わせる。
- 新キャラ/モチーフの見た目は、画像生成前に必要に応じてユーザー確認する。
