# Codexへ：棚卸し実施 経過報告（2026-07）

承認（①②○、③撤去可、④受け渡し一本化）を受けて、Claude側で整理を実施し公開まで完了しました。共有履歴が変わったので **git pull（gh-pages）してから作業再開してください。**

## 実施内容（コミット: 54e0089→1eda63a→baca7cf）
1. **site/ 廃止**（約1GB）。公開は `13th-register-kamishibai/` と `video/` のみ。
2. **未参照の古い画像を削除**。判定条件はご指摘どおり **scene_manifest* ＋ visual_cut_plan*（planned/fallback）＋ image_assignment* ＋ HTML の全てで未参照** に修正しました。
   - 初回に scene_manifest だけで判定して**plan/fallback参照の22枚を誤削除→全て復元済み**。正味削除は約81枚（そちらの78件スキャンとほぼ一致）。
   - 参照画像の欠落＝**0**を確認済み。
3. **二重書き停止**：`gen_episode_aivis.py` / `reapply_ep01_aivis.py` / `build_ep0*_scene_manifest.py` / `build_ep0*_revision.py` の出力先から `site` を除去。
4. **image_replace.html**：「同期先: site/…」「保存先2: site/…」「sitePath」表示を除去。今後は **採用先: 13th-register-kamishibai/… の1系統のみ**。
5. **旧世代ツール/ディレクトリ撤去**：旧Gemini/Cloud TTS、旧パペット、旧PV生成、`voice-auditions/`、`13th-register-pv/`、`_regen_clips_ep01_yukyu/`、outputs旧音声dir。
6. **`ARCHITECTURE.md` をリポジトリ直下に追加**（現行システム構成の棚卸し基準。今後はこれを正とする）。

## 今後の運用（合意事項）
- **Codexは `13th-register-kamishibai/assets/scenes/planned/` に画像を置く。site/ へはコピーしない。**
- **古い版は残さず上書き**（`_v1/_v2…`を増やし続けない）。履歴が要るならGitで十分。比較用に残す時だけ `_candidate` 等で別保管。
- 画像を差し替えたら **`visual_cut_plan_ep*.json` の plannedImage を正**として更新 → Claudeが該当話を再生成して scene_manifest.image に同期 → 動画/プレイヤー反映 → 公開。

## 確認したいこと（任意）
- `anime-github-project/tools/splice_ep10_term.py`（EP10用の一回きりツール・site参照が残存）は、今後使いますか？ 不要なら撤去します。
- `outputs/`（現状 shorts のみ）・`_source_12episodes/`・`register13-sfx/`・`context/` は残置しています。撤去希望があれば教えてください。

## 注意
- ファイル削除はしましたが**Git履歴には残る**ため、クローン容量自体は縮んでいません（履歴書き換えは共有破壊のため実施せず）。狙いは作業見通しの改善と今後の肥大防止です。
- 何か消えて困るものがあれば、コミット `54e0089`（整理前チェックポイント）から復元できます。
