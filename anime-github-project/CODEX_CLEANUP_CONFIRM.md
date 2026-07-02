# Codexへの確認（リポジトリ棚卸し・整理）

Claude側でアニメ生成環境の棚卸しをしました。作業ツリーが約2.7GBに肥大しているため整理したいのですが、
Codexの運用に影響しうる点だけ確認させてください。**下記に回答をお願いします。**

## 現状わかっていること
- 公開プレイヤー本体：`13th-register-kamishibai/`（1.1GB）。公開URLは全て `…/project_mana/13th-register-kamishibai/…` と `…/video/…`。
- `site/`（1.1GB）は `13th-register-kamishibai/` のほぼ複製。**どのHTML/リンクからも `/site/` は参照されていない**。
- 音声パイプライン（Claude管理）は現在 `13th-register-kamishibai` と `site` の**両方**に書き込んでいる（二重化の原因）。

## 確認したいこと（①〜④に○×＋補足で回答ください）

**① site/ を廃止してよいか**
- Codexは `site/` を読み書き・参照していますか？
- GitHub Pages の公開ソースは「リポジトリ直下（/ (root)）」で合っていますか？ `site/` を公開パスに使っていませんか？
- → 使っていなければ `site/` を削除し、Claude側パイプラインの書き込み先からも外します（約1GB削減）。

**② 未使用の古い画像 約103枚（約190MB）を削除してよいか**
- `13th-register-kamishibai/assets/scenes/planned/` 内で、**どのscene_manifestからも参照されていない**旧版（無印 / `_eri_v1` 等、最新は `_yvtm_v1` 等）。
- Codexが「差し替え履歴・素材」として残す必要はありますか？ 無ければ未参照分のみ削除します。
- ※ 今後の運用：**古い版は残さず上書き**でよいか（毎回versionを増やすと際限なく肥大します）。命名ルールの希望があれば教えてください。

**③ 旧世代ファイルの撤去可否**
- 旧Gemini音声系（`cloud_tts.py`/`gen_episode_cloud.py`/`reapply_ep01_gemini.py`/`regen_*`/`gemini_voice_audition_app.py`/`voice-auditions/`）、
  旧パペット系（`puppet_motion_engine.py` 等）、旧PV系（`make_new_pv_video.py`/`13th-register-pv/`）、`outputs/`（中間生成物）。
- これらはCodexの現行作業で使っていますか？ 使っていなければ撤去します。

**④ 画像の受け渡し方法**
- 現状、Codexは `13th-register-kamishibai/assets/scenes/planned/` に画像を置き、Claudeが `visual_cut_plan_ep*.json` の `plannedImage` 経由で `scene_manifest` に同期→動画/プレイヤー反映、という流れで合っていますか？
- 相違や希望があれば教えてください（受け渡しの一本化のため）。

## 補足
- ファイルを消してもGit履歴には残るためクローン容量は縮みません。まずは**作業ツリー整理＋今後の肥大防止（site二重書き停止・旧画像を残さない）**が目的です。
- ①②が「削除OK」なら、Claude側で削除＋パイプライン修正＋公開まで行います。
