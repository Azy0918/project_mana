# 全話画像設計インデックス

第3〜12話の画像生成前設計ファイル一覧。画像生成は未実行。

| 話 | タイトル | 台帳 | visual_cut_plan | image_assignment |
|---:|---|---|---|---|
| 3 | 昨日に溶けるアイスクリーム | `ep03_image_cut_ledger.md` | `visual_cut_plan_ep03.json` | `image_assignment_ep03.json` |
| 4 | 未来レシートは先に謝る | `ep04_image_cut_ledger.md` | `visual_cut_plan_ep04.json` | `image_assignment_ep04.json` |
| 5 | 昭和の伝票、まだ未処理です | `ep05_image_cut_ledger.md` | `visual_cut_plan_ep05.json` | `image_assignment_ep05.json` |
| 6 | 賞味期限が生まれる前のパン | `ep06_image_cut_ledger.md` | `visual_cut_plan_ep06.json` | `image_assignment_ep06.json` |
| 7 | 宇宙宅配便、店留めです | `ep07_image_cut_ledger.md` | `visual_cut_plan_ep07.json` | `image_assignment_ep07.json` |
| 8 | 月面店、発注しすぎました | `ep08_image_cut_ledger.md` | `visual_cut_plan_ep08.json` | `image_assignment_ep08.json` |
| 9 | 銀河ポイントカードはお持ちですか？ | `ep09_image_cut_ledger.md` | `visual_cut_plan_ep09.json` | `image_assignment_ep09.json` |
| 10 | あの会社員、返品済みです | `ep10_image_cut_ledger.md` | `visual_cut_plan_ep10.json` | `image_assignment_ep10.json` |
| 11 | 第十二レジと第十四レジ | `ep11_image_cut_ledger.md` | `visual_cut_plan_ep11.json` | `image_assignment_ep11.json` |
| 12 | 午前二時十七分、通常営業です | `ep12_image_cut_ledger.md` | `visual_cut_plan_ep12.json` | `image_assignment_ep12.json` |

## 運用

- `image_assignment_epXX.json` が画像割り当ての正本。
- Claudeはこのファイルを読み、assignmentsの中身は編集しない。
- 正式line ID確定後、Codexがassignmentsを更新する。
- 画像生成は各話の台本・音声・タイミング確定後に実行する。
