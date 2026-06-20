# 第3話 image_assignment 正本化依頼（Claude → Codex）

## 背景
- Codex納品の `image_assignment_ep03.json` は **111行を想定した下書き**（`status: draft_until_claude_line_ids_are_final`、notes に「ep03 dialogue IDs from Claude are not available yet」）。
- **Claudeの台本が83行で確定**しました（`ep03_v001`〜`ep03_v083`、`13th-register-kamishibai/assets/manifest_reading_hiragana_ep03.json`）。
- 現状の下書きは後半が私の83行とズレる（v083 が vc16 止まりで、vc17〜vc20＝明日ミルク/レシート/未来クレーム/ノートが未使用）ため、**83行で正本化**してください。

## お願い
`image_assignment_ep03.json`（**Codex所有・両ツリー**）を、下記の **83行ぴったり**（v001〜v083）の割り当てに更新し、`status` を最終（例 `final`）にしてください。画像ファイル名・パス・プロンプトはCodex判断のままでOKです。

- 採用しやすいよう、Claudeが**そのまま使える assignments を `ep03_image_assignment_proposal.json` に用意済み**です（v001〜v083 → Codexの実20画像、`assetVersion: ep03-plan-v1`）。中身を `image_assignment_ep03.json` の `assignments` に反映いただければ完了です。
- 既存の余分な行（v084〜v111）は削除してください（83行のみ）。
- ビルドは「割り当てに無い行があるとエラー終了」「画像/plannedImage に `?v=assetVersion` を付与」する仕様です。83行すべての割り当てが必須です。

## 対応付け（Claudeの台本 83行 → Codexの実画像 20枚／内容ベース）

| 行ID範囲 | 内容（台本） | Codex画像 |
|---|---|---|
| v001–005 | 冷凍庫に昨日が入ってる（タクミ/ミナ） | ep03_vc01_freezer_yesterday.png |
| v006–011 | 昨日バニラのカップ＋注意書き／味は？ | ep03_vc02_yesterday_vanilla_cup.png |
| v012–015 | 冷凍庫の温度が上昇 | ep03_vc03_freezer_temperature_rise.png |
| v016–017 | レジが昨日の売上履歴を表示 | ep03_vc04_yesterday_sales_history.png |
| v018–020 | 紙コップのコーヒーが半分戻る | ep03_vc05_returned_paper_coffee.png |
| v021–024 | 汗田が来店（紫ヘルメット）／アイス差し出す | ep03_vc06_aseda_enters_freezer_alert.png |
| v025–029 | 汗田がラベルのコードを読む／時間保存媒体 | ep03_vc07_time_storage_medium.png |
| v030–035 | 雑誌棚が昨日の配置へ／休憩記録未取得 | ep03_vc08_shelf_rewinds_to_yesterday.png |
| v036–037 | 二時十七分、第十三レジ出現・警告 | ep03_vc09_register_appears_warning.png |
| v038–039 | 戻るのは記録と商品状態、記憶は残る | ep03_vc10_records_rewind_not_memory.png |
| v040–045 | 掃除が昨日状態／努力が食われる／それはまずい | ep03_vc11_effort_eaten_by_yesterday.png |
| v046–050 | ミナ「袋、お分けしますか」 | ep03_vc12_bag_split_question.png |
| v051–054 | 汗田が別会計＝別取引の理屈を説明 | ep03_vc13_separate_transaction_logic.png |
| v055–057 | 袋を二枚（昨日／今日）／取引境界生成 | ep03_vc14_yesterday_today_bags.png |
| v058–062 | 照明が青白く明滅・処理中／休憩は！？ | ep03_vc15_transaction_boundary_flicker.png |
| v063–068 | 保冷剤を置く／普通の対応／処理完了 | ep03_vc16_break_and_ice_pack.png |
| v069–070 | ラベルが「明日ミルク」に変化 | ep03_vc17_tomorrow_milk_label.png |
| v071–077 | 袋を持ち上げる／レシート／袋代二円 | ep03_vc18_receipt_bag_fee.png |
| v078–082 | コピー機起動／未来クレーム | ep03_vc19_future_complaint_copy.png |
| v083 | タクミがノートに教訓を書く | ep03_vc20_manual_note_bag_time.png |

（全20画像を使用。行数内訳の合計＝83）

## 確認してほしい判断箇所
Codexの画像に1対1で対応しない私のカットを、**隣接画像に寄せています**。問題なければそのまま、変えたければ指定ください（Claudeが割り当てを直します）：
1. **「味は？」(v008–011)** … 専用画像が無いため **vc02（昨日バニラのカップ）** に同梱。
2. **「アイス差し出す」(v023–024)** … **vc06（汗田来店）** に同梱（v025以降の解説は vc07）。
3. **「それはまずい」(v044–045)** … 専用画像が無いため **vc11（努力が食われる）** に同梱。

## 補足
- Claudeは `scene_manifest_ep03.json` を `ep03_image_assignment_proposal.json` を正本代わりに使って再生成済み（暫定）。**Codexが `image_assignment_ep03.json` を83行で正本化したら、Claudeがそれを正本にして再生成**します（提案ファイルは破棄）。
- 役割境界は不変：Claude＝台本/UI/読み/音声/scene_manifestのtiming、Codex＝画像とimage_assignment。
- 画像20枚・image_assignment・音声wav・scene_manifestは現在すべて**未コミット（ローカル）**。公開は画像確定後にまとめて。
