# 第6話 画像カット台帳

対象: 第6話「賞味期限が生まれる前のパン」

## 状態

- 全話先行準備として、シナリオ本文からCodex側の画像設計を作成。
- 画像生成はまだ実行しない。台本・音声・正式line ID確定後に開始する。
- `image_assignment_ep06.json` は正式line ID確定前の `ep06_v001-v100` 仮IDベース。

## 新キャラ / モチーフ設定案

- 唐沢栄治を初登場/固定キャラとして使用。賞味期限未成立パン、保留箱、付箋が主要モチーフ。
- 中心業務/モチーフ: 日付管理・廃棄判断・保留箱

## 画像生成時の注意点

- 画像内に字幕、会話ウィンドウ、時計、アプリUIを描かない。
- 9:16縦型。主要被写体は中央寄り。下部30〜40%は字幕UIセーフエリアとして重要物を置かない。
- 既存キャラは `character_visual_locks.json` 準拠。顔、髪型、制服、小道具、レジ外観を固定。
- レシートや端末の長文は読ませようとしない。必要ならHTML字幕/ログで表示する前提。
- 新モチーフは小さく扱い、急に巨大化させない。深夜コンビニの普通さとSF異常の同居を守る。

## 20カット採用計画

| cut | タイトル | 採用予定ファイル | 台本行ID範囲(仮) | 内容 |
|---:|---|---|---|---|
| 01 | パン棚の白い紙袋 | `assets/scenes/planned/ep06_vc01_plain_bread_bags.png` | `ep06_v001-ep06_v005` | 午前二時九分、パン棚の奥に白い無印刷の紙袋が並ぶ。赤いスタンプだけがある。 |
| 02 | 賞味期限がない | `assets/scenes/planned/ep06_vc02_no_expiration_date.png` | `ep06_v006-ep06_v010` | タクミが白い紙袋を持ち、賞味期限がないことに困惑。エリは昔のパンかと淡々。 |
| 03 | 古い紙と焼きたて匂い | `assets/scenes/planned/ep06_vc03_old_paper_fresh_smell.png` | `ep06_v011-ep06_v015` | 古い乾いた紙袋なのに焼きたての匂いがする不思議なパン。湯気と古紙感の矛盾。 |
| 04 | 第十三レジ概念前商品 | `assets/scenes/planned/ep06_vc04_pre_concept_register.png` | `ep06_v016-ep06_v020` | 二時十七分、第十三レジが賞味期限概念成立前の商品を確認する。 |
| 05 | 思い出鮮度 | `assets/scenes/planned/ep06_vc05_memory_freshness.png` | `ep06_v021-ep06_v025` | 第十三レジに思い出鮮度高のような表示。タクミが商品管理に入れないでと反応。 |
| 06 | 汗田の判断基準分析 | `assets/scenes/planned/ep06_vc06_aseda_old_criteria.png` | `ep06_v026-ep06_v030` | 汗田がパンを見て、腐敗ではなく判断基準が古いと説明する。 |
| 07 | パンの自己主張 | `assets/scenes/planned/ep06_vc07_bread_speaks.png` | `ep06_v031-ep06_v035` | パン袋が震え、まだ誰かの朝ごはんになれる雰囲気の文字が浮かぶ。文字は雰囲気。 |
| 08 | 廃棄か販売か | `assets/scenes/planned/ep06_vc08_sell_or_discard_problem.png` | `ep06_v036-ep06_v040` | 販売すると表示ルール違反、廃棄すると善意記録消失。タクミがどちらも困る顔。 |
| 09 | 試食案 | `assets/scenes/planned/ep06_vc09_taste_test_bad_idea.png` | `ep06_v041-ep06_v045` | エリが試食案を出し、タクミが実験台にしないでと引く。パンと端末。 |
| 10 | 唐沢来店 | `assets/scenes/planned/ep06_vc10_karasawa_enters_audit.png` | `ep06_v046-ep06_v050` | 唐沢栄治が深夜巡回のついでに来店。棚割りと廃棄率を見ている冷静な本部SV。 |
| 11 | 売場には出せません | `assets/scenes/planned/ep06_vc11_karasawa_no_sale.png` | `ep06_v051-ep06_v055` | 唐沢が賞味期限表示なしのパンを見て、売場には出せないと判断。 |
| 12 | 廃棄理由不明は保留 | `assets/scenes/planned/ep06_vc12_hold_unknown_discard.png` | `ep06_v056-ep06_v060` | 唐沢が廃棄理由不明はまず保留、記録を残すと指示。汗田が現実監査の強さを見る。 |
| 13 | 保留処理受理 | `assets/scenes/planned/ep06_vc13_pending_register_accept.png` | `ep06_v061-ep06_v065` | 第十三レジが販売不可、廃棄不可、現代店舗保留を受理。 |
| 14 | 付箋を貼る | `assets/scenes/planned/ep06_vc14_sticky_note_on_bread.png` | `ep06_v066-ep06_v070` | タクミが販売しない・捨てない・触りすぎない、の付箋をパン袋に貼る。 |
| 15 | 未来が付箋で安定 | `assets/scenes/planned/ep06_vc15_future_stabilized_by_note.png` | `ep06_v071-ep06_v075` | 付箋を貼ったパン袋の光が落ち着き、未来の一部が安定する。 |
| 16 | 未成立パンレシート | `assets/scenes/planned/ep06_vc16_pre_expiration_receipt.png` | `ep06_v076-ep06_v080` | 賞味期限未成立パン、販売不可、廃棄不可、唐沢指摘有効のレシート。 |
| 17 | バックヤード明記 | `assets/scenes/planned/ep06_vc17_backyard_notice.png` | `ep06_v081-ep06_v085` | 唐沢が店長確認未了ならバックヤードに明記と普通に指摘。 |
| 18 | 保留箱へ | `assets/scenes/planned/ep06_vc18_pending_box_bread.png` | `ep06_v086-ep06_v090` | エリが保留箱を棚に置き、パンを朝まで保管する。 |
| 19 | 店長確認待ち | `assets/scenes/planned/ep06_vc19_waiting_manager_confirmation.png` | `ep06_v091-ep06_v095` | 保留箱、付箋、バックヤード棚。永遠に来ない気がする店長確認の空気。 |
| 20 | マニュアル廃棄判断 | `assets/scenes/planned/ep06_vc20_manual_hold_note.png` | `ep06_v096-ep06_v100` | タクミが判断できないものは保留、売れないものは売らないとマニュアルに書く。 |

## 保留事項

- Claudeの正式な台本行IDが出たら、assignmentsを正式IDに合わせる。
- 新キャラ/モチーフの見た目は、画像生成前に必要に応じてユーザー確認する。
