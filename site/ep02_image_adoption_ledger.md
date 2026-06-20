# 第2話 画像採用台帳

この台帳は画像担当（Codex）が管理する。Claude はこの台帳と `build_ep02_scene_manifest.py` の画像マッピングに従って `scene_manifest_ep02.json` を再生成する。

## 同期方針

- 正本: `13th-register-kamishibai/`
- 互換: `site/`
- 画像本体、`visual_cut_plan_ep02.json`、`assets/ep02_visual_cut_plan.csv`、この台帳は両ツリーで同期する。
- `scene_manifest_ep02.json` の `id` / `cut` / `start` / `end` / `speaker` / `dialogue` / `reading` / `log` / `visualLabel` / `progressLabel` は Claude 担当。
- `scene_manifest_ep02.json` の `image` / `plannedImage` / `imagePrompt` は画像担当のマッピングから生成する。

## 採用判断

| cut | 内容 | 採用ファイル | 採否 | 新規生成 | 備考 |
| --- | --- | --- | --- | --- | --- |
| cut01 | 会社の駐輪場 / v002b 回想ナレ含む | `ep02_vc01_company_parking_asada.png` | 採用 | 不要 | v002b「役員の言葉が、まだ耳に残っていた。」は既存流用で成立。 |
| cut17 | ナビが感謝 / 汗田が黙る | `ep02_vc13_future_thanks.png` | 採用 | 不要 | `ep02_vc17_cleaning_first.png` は清掃の絵で内容不一致。現状は vc13 を使う。 |
| cut18 | コーヒーのやりとり | `ep02_vc14_black_coffee.png` | 採用 | 保留 | 内容は vc14 が合う。ただし既存絵はコーヒー二重持ち疑いがあるため、後で画像改修候補。 |
| cut19 | レシート排出 / v056b 店長確認未了含む | `ep02_vc15_operation_log.png` | 採用 | 不要 | v056b「店長確認、未了」は operation_log のレシート絵で成立。 |

## 現時点の判断

- cut17 は `ep02_vc13_future_thanks.png` を採用。
- cut18 は `ep02_vc14_black_coffee.png` を採用。ただし絵の中の持ち物整合は後日QA対象。
- v002b は `ep02_vc01_company_parking_asada.png` 流用で新規生成不要。
- v056b は `ep02_vc15_operation_log.png` 流用で新規生成不要。

## Claudeへの通知事項

- cut17/cut18 は画像番号と manifest cut 番号が一致しない明示マッピングとして維持する。
- Claude が台本・タイミング調整で `build_ep02_scene_manifest.py` を実行する場合、画像計画を上書きしないため `--no-visual-plan` を付ける。
- 画像差し替えが発生した場合、Codex はこの台帳と `visual_cut_plan_ep02.json` を更新してから Claude へ通知する。
