# 第12話 画像カット台帳

対象: 第12話「午前二時十七分、通常営業です」

## 状態

- 全話先行準備として、シナリオ本文からCodex側の画像設計を作成。
- 画像生成はまだ実行しない。台本・音声・正式line ID確定後に開始する。
- `image_assignment_ep12.json` は正式line ID確定前の `ep12_v001-v100` 仮IDベース。

## 新キャラ / モチーフ設定案

- 最終回。既存主要キャラ全員と過去モチーフ総出演。新キャラ追加なし。
- 中心業務/モチーフ: レジ締め・日次精算・最終保留

## 画像生成時の注意点

- 画像内に字幕、会話ウィンドウ、時計、アプリUIを描かない。
- 9:16縦型。主要被写体は中央寄り。下部30〜40%は字幕UIセーフエリアとして重要物を置かない。
- 既存キャラは `character_visual_locks.json` 準拠。顔、髪型、制服、小道具、レジ外観を固定。
- レシートや端末の長文は読ませようとしない。必要ならHTML字幕/ログで表示する前提。
- 新モチーフは小さく扱い、急に巨大化させない。深夜コンビニの普通さとSF異常の同居を守る。

## 20カット採用計画

| cut | タイトル | 採用予定ファイル | 台本行ID範囲(仮) | 内容 |
|---:|---|---|---|---|
| 01 | 静かすぎる午前二時 | `assets/scenes/planned/ep12_vc01_too_quiet_store.png` | `ep12_v001-ep12_v005` | 午前二時、国道沿いのコンビニがいつもより静か。冷蔵ケースの音まで緊張している。 |
| 02 | 夜勤マニュアル総復習 | `assets/scenes/planned/ep12_vc02_manual_recap.png` | `ep12_v006-ep12_v010` | タクミがバックヤードのマニュアルノートを開き、これまでの教訓が積み上がっている。 |
| 03 | 全員集合の店内 | `assets/scenes/planned/ep12_vc03_all_characters_present.png` | `ep12_v011-ep12_v015` | 未来青年、汗田、唐沢、座木山がそれぞれ店内にいる。全員必要そうな緊張感。 |
| 04 | 二時十七分一斉鳴動 | `assets/scenes/planned/ep12_vc04_devices_all_ring.png` | `ep12_v016-ep12_v020` | 二時十七分、第十三レジ出現と同時にコピー機、発注端末、宅配端末、ホットスナックケース、廃棄ボックスが一斉に鳴る。 |
| 05 | 伝票が雪のように降る | `assets/scenes/planned/ep12_vc05_slips_fall_like_snow.png` | `ep12_v021-ep12_v025` | 未来、過去、宇宙、パラレルワールドの伝票が雪のように店内へ降る。 |
| 06 | 全モチーフ集結 | `assets/scenes/planned/ep12_vc06_all_motifs_gather.png` | `ep12_v026-ep12_v030` | 完全栄養おにぎり、昨日バニラ、昭和伝票、未成立パン、宇宙宅配便、酸素グミ、銀河ポイントなどが並ぶ。 |
| 07 | 最終処理選択肢 | `assets/scenes/planned/ep12_vc07_final_processing_choices.png` | `ep12_v031-ep12_v035` | 第十三レジが削除、未来へ返品、銀河流通監査局へ返送、現代店舗で保留を提示。 |
| 08 | 未来青年の問い | `assets/scenes/planned/ep12_vc08_future_worker_question.png` | `ep12_v036-ep12_v040` | 未来青年が未来へ戻れば全部思い出すのかと震える。首元タグが剥がれそうに光る。 |
| 09 | 救う知識と戦争の知識 | `assets/scenes/planned/ep12_vc09_knowledge_duality.png` | `ep12_v041-ep12_v045` | 第十三レジが食糧不足を救う知識と物流戦争を起こす知識が同時に復元されると示す。 |
| 10 | 汗田の技術と人間 | `assets/scenes/planned/ep12_vc10_aseda_tech_human.png` | `ep12_v046-ep12_v050` | 汗田が技術も人間も廃棄か返品だけで扱うものではないと静かに言う。 |
| 11 | 銀河監査局通知 | `assets/scenes/planned/ep12_vc11_galactic_audit_final.png` | `ep12_v051-ep12_v055` | コピー機から銀河流通監査局の返送要求通知が出る。BGMが眠い指摘も混ざるが絵は不穏。 |
| 12 | 唐沢の現金過不足ゼロ | `assets/scenes/planned/ep12_vc12_karasawa_cash_zero.png` | `ep12_v056-ep12_v060` | 唐沢が現金表を見ながら、数字が合わないものは保留、現金過不足はゼロと現実判断。 |
| 13 | 残り時間一分 | `assets/scenes/planned/ep12_vc13_one_minute_left.png` | `ep12_v061-ep12_v065` | 第十三レジが残り時間一分を示し、店内の全員が集中する。 |
| 14 | 保留です | `assets/scenes/planned/ep12_vc14_takumi_says_hold.png` | `ep12_v066-ep12_v070` | ミナの問いにタクミが自然に保留ですと答える。成長の瞬間。 |
| 15 | 現代店舗で保留を押す | `assets/scenes/planned/ep12_vc15_mina_pushes_hold.png` | `ep12_v071-ep12_v075` | ミナが第十三レジ画面で現代店舗で保留を押す。 |
| 16 | 未来大戦争発生保留 | `assets/scenes/planned/ep12_vc16_war_on_hold.png` | `ep12_v076-ep12_v080` | 店内の空気が揺れ、銀河標準からあげや廃棄予定の未来が光って折り畳まれる。 |
| 17 | タグ安定 | `assets/scenes/planned/ep12_vc17_memory_tag_stabilizes.png` | `ep12_v081-ep12_v085` | 未来青年の首元タグが剥がれず透明なまま安定する。汗田がコーヒーを渡す。 |
| 18 | 最後のレシート | `assets/scenes/planned/ep12_vc18_final_receipt.png` | `ep12_v086-ep12_v090` | 危険知識封印、未来大戦争発生保留、青年返品取消、現金過不足ゼロ、本日の営業継続中の最後のレシート。 |
| 19 | 第十三レジ消失と通常音 | `assets/scenes/planned/ep12_vc19_register_disappears_normal_sound.png` | `ep12_v091-ep12_v095` | 午前二時二十分、第十三レジが消え、冷蔵ケース、自動ドア、小さな電子音が戻る。 |
| 20 | 夜勤は終わらない | `assets/scenes/planned/ep12_vc20_night_shift_never_ends.png` | `ep12_v096-ep12_v100` | 座木山がコピー機を使えるか聞き、コピー機が普通でない音を鳴らす。ミナがモップ、タクミが最後に夜勤は終わらないと書く。 |

## 保留事項

- Claudeの正式な台本行IDが出たら、assignmentsを正式IDに合わせる。
- 新キャラ/モチーフの見た目は、画像生成前に必要に応じてユーザー確認する。
