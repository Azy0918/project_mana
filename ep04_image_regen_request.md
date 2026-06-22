# 第4話 画像 再生成依頼（デスクトップCodex用）

あなたのデスクトップCodexで再生成 → 保存。終わったらClaudeが後工程（site同期・image_assignment確認・scene_manifest再生成・`?v`更新・公開）を担当します。

## 参照ファイル（リポジトリ内）
- `13th-register-kamishibai/visual_cut_plan_ep04.json` … 各カットの場面プロンプト
- `13th-register-kamishibai/character_visual_locks.json` … キャラのlock。**`truck_driver_ep04`（トラック運転手）を新規追加済み**

## スタイル（重要）
- **詳細アニメ／ビジュアルノベルCG調**（キャラシートや、良かった vc01・vc13・vc14 と同じ描き込み密度）。
- **フラット／ベクター／ミニマル／フラットデザイン調にしない**（前回これで失敗）。
- 各カットの生成プロンプトに、**そのカットに登場するキャラ全員のlockPrompt**を必ず含める。

## 維持（再生成不要・良かったもの）
- **vc01 / vc13 / vc14**（気に入らなければ再生成可）

## 再生成する17カット ＋ 重点修正
保存先：`13th-register-kamishibai/assets/scenes/planned/` に**下記の正確なファイル名で上書き保存**。

| カット | ファイル名 | 重点 |
|---|---|---|
| vc02 | ep04_vc02_future_complaint_print.png | |
| vc03 | ep04_vc03_hot_snack_case.png | |
| vc04 | ep04_vc04_zakiyama_copy_visit.png | 客＝**座木山**（zakiyama lock：痩せ型・釣りベスト・乱れ髪） |
| vc05 | ep04_vc05_pre_apology_notice.png | |
| vc06 | ep04_vc06_register_appears_complaint.png | **第十三レジlock厳守**（黒セルフレジ・シアンの横目2本・小さな口） |
| vc07 | ep04_vc07_aseda_log_analysis.png | 汗田lock |
| vc08 | ep04_vc08_karaage_pre_apology.png | |
| vc09 | ep04_vc09_future_manual_basic_greeting.png | 第十三レジlock |
| vc10 | ep04_vc10_truck_driver_enters.png | **運転手＝`truck_driver_ep04` lock**（恰幅・白髪角刈り・赤ら顔・作業つなぎ／**座木山に似せない**） |
| vc11 | ep04_vc11_takumi_serves_karaage.png | 同上（運転手lock） |
| vc12 | ep04_vc12_memory_temperature_matches.png | 同上（運転手lock） |
| vc15 | ep04_vc15_apology_time_return.png | **第十三レジlock厳守**（前回レジのデザインが崩れていた） |
| vc16 | ep04_vc16_complaint_receipt.png | レシート（文字は作り込みすぎない） |
| vc17 | ep04_vc17_future_worker_hint.png | |
| vc18 | ep04_vc18_zakiyama_blackwhite_map.png | 座木山lock＋白黒地図 |
| vc19 | ep04_vc19_manual_complaint_note.png | |
| vc20 | ep04_vc20_night_shift_after_complaint.png | 夜勤の締め（前回暗すぎ・軽量だった） |

## 任意
- `assets/character_sheets/truck_driver_ep04_sheet.png` … キャラ表用の運転手シート（作れば「キャラ表」が11人で揃う）

## 共通の禁止
- 画像内に字幕・UI文字・時計を描かない。9:16縦。上端の角と下部30〜40%に重要要素を置かない。

## 完了後
「画像できた」と言ってください。私が **site/へ同期 → image_assignment_ep04 確認 → scene_manifest_ep04 再生成 → `?v` 更新（キャッシュ差し替え）→ 公開** まで実行します。
