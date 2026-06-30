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

## 2026-06-30 タイミング修正

- `scene_manifest_ep02.json` の画像切り替えをセリフ内容ベースで再割り当てした。
- v012 は夜の国道へ走り出すセリフなので `vc03 夜の国道へ` に戻した。
- v013-v018 はレシート保管の会話なので `vc04 レシートの保管` に戻した。
- v019-v022 は汗田来店と第十三レジの有無を尋ねる場面なので `vc05 汗田、来店` に戻した。
- v023-v024 は第十三レジ出現なので `vc06 第十三レジ出現` に戻した。
- v025-v027 はナビ接続なので `vc07 ナビとの接続` に戻した。
- v028-v030 は在庫予測モデルの判定なので `vc08 在庫予測モデル` に戻した。
- v031-v039 は履歴メモの欠損と条件不足なので `vc09 欠けた履歴メモ` に戻した。
- v040-v043 は汗田が修正メモを書く場面なので `vc10 修正メモを書く` に戻した。
- v044-v046 は「数値だけじゃ決まらない」の場面なので `vc11 数値だけじゃない` に戻した。
- v047-v050 は修正メモ受理なので `vc12 メモ受理` に戻した。
- v051-v055 はナビからの感謝なので `vc13 未来からの感謝` に戻した。
- v056-v062 はブラックコーヒーと会計のやりとりなので `vc14 ブラックで` に戻した。
- v063-v067 は履歴メモ保全とレシート排出なので `vc15 吐き出されたレシート` に戻した。
- v068-v069 は冷凍庫の青いラベルと次回予告反応なので `vc16 冷凍庫の青いラベル` に戻した。
- v070-v073 は掃除優先の会話なので `vc17 清掃へ戻る` に戻した。
- v074 は汗田退店なので `vc18 汗田、退店` に戻した。
- v075-v076 はナビ端の次異常地点表示なので `vc19 次の異常地点ナビ` に戻した。
- 現行セリフでは `vc20 夜勤は続く` 専用の独立した発話がないため、最後は内容一致を優先してナビ絵で締める。

## Claudeへの通知事項

- cut17/cut18 は画像番号と manifest cut 番号が一致しない明示マッピングとして維持する。
- Claude が台本・タイミング調整で `build_ep02_scene_manifest.py` を実行する場合、画像計画を上書きしないため `--no-visual-plan` を付ける。
- 画像差し替えが発生した場合、Codex はこの台帳と `visual_cut_plan_ep02.json` を更新してから Claude へ通知する。
