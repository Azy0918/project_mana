# 深夜二時の第十三レジ ｜ システム構成（現行 2026-07）

紙芝居アニメ（縦9:16 / YouTube想定）の生成・公開パイプライン。**Codex＝画像担当 / Claude＝音声・字幕・動画・公開担当**の協業。

## 公開（GitHub Pages / gh-pages ブランチ）
- 本体プレイヤー：`13th-register-kamishibai/`（`index.html` + `assets/` + 各`scene_manifest*.json`）
- 動画：`video/ep0N_youtube_vertical_1080x1920.mp4`
- レビュー/依頼アプリ：`13th-register-kamishibai/review.html`（試聴あり・ローカル用）/ `review_public.html`（試聴なし・公開用）
- 画像受け渡し：`13th-register-kamishibai/image_replace.html`（Codex向け差し替え指示生成）
- 公開URL基点：`https://azy0918.github.io/project_mana/`
- **※ `site/` は廃止（旧ミラー）。公開はリポジトリ直下から。二重書きしない。**

## データ（真実の источник）
- `13th-register-kamishibai/scene_manifest.json`(EP01) / `scene_manifest_ep02..12.json`：各行 id/speaker/dialogue/visualCutId/image/start/end。**プレイヤー・動画の元**。
- `13th-register-kamishibai/visual_cut_plan_ep*.json`：カット定義（plannedImage/fallbackImage）。Codexが画像を差し替えたらここを更新。
- `13th-register-kamishibai/assets/*.wav`：各話の連結音声。`assets/manifest_reading_hiragana_*.json`：review.htmlが読む「よみ」表示源。
- `anime-github-project/ep01_revised.md`：EP01台本正本（`話者：表示セリフ｜読み` 形式）。
- `anime-github-project/tools/ep01_voice_cast.csv`：AivisSpeechキャスト（話者/style_id/速度/抑揚/ピッチ等）。
- `anime-github-project/tools/line_reading_overrides.json`：行単位の読み上書き（表示≠読み。時空→じくう等の発音矯正・読点調整）。
- `anime-github-project/tools/sfx_register.wav`：第13レジ登場の効果音。

## 生成パイプライン（Claude）
| 目的 | スクリプト | 出力 |
|---|---|---|
| EP01 音声再生成 | `tools/reapply_ep01_aivis.py`（`ep01_revised.md`＋cast） | scene_manifest.json＋wav＋voice manifest |
| EP02-12 音声再生成 | `tools/gen_episode_aivis.py <ep>`（scene_manifest＋cast＋overrides） | 同上（画像はvisual_cut_planから再同期） |
| 本編動画 | `tools/build_episode_video.py <ep>`（imageio_ffmpeg・BGM/字幕付き） | `video/ep0N_...mp4` |
| ショート | `tools/build_ep0N_short*.py` | `outputs/shorts/` ほか |
| ローカル配信 | `tools/serve_range.py 8013 <repoルート>` | `http://localhost:8013/13th-register-kamishibai/` |
| 声/テンポ調整 | `tools/aivis_tuner_server.py`（:8030） | cast CSV更新 |

- 音声エンジン：**AivisSpeech**（127.0.0.1:10101）。話者一貫。※Gemini/Cloud TTSは廃止。
- 字幕折り返し：`build_episode_video.py` の `wrap_jp`（枠幅いっぱい＋行頭禁則＋半角英数字連結）。

## 発音（読み）の扱い
- 表示（字幕）は漢字のまま、音声（読み）だけ矯正する二層構造。
- EP01：`ep01_revised.md` の `表示｜読み`。EP02-12：`line_reading_overrides.json`＋`gen_episode_aivis`のREADING_FIXES辞書（時空→じくう/履歴→りれき/返金→へんきん/返品→へんぴん/汗田→あせだ）。

## 画像の流れ（Codex→Claude）
1. Codexが `13th-register-kamishibai/assets/scenes/planned/` に画像を置く（**古い版は残さず上書き推奨**）。
2. Codexが `visual_cut_plan_ep*.json` の `plannedImage` を更新。
3. Claudeが該当話を再生成（`gen_episode_aivis`が visual_cut_plan→scene_manifest の image を同期）→ 動画/プレイヤー反映→公開。

### 画像生成前チェック
- 座木山辰哉など固定キャラを含む画像生成前に `python 13th-register-kamishibai/tools/check_visual_prompt_locks.py` を実行する。
- 座木山の正本は `assets/character_reference.json` と `character_visual_locks.json`。旧設定（暗いフーディー、黒い長靴、店内の釣り竿・タモ網・バケツ・クーラーボックス）をプロンプト本文へ復活させない。
- `apply_character_references.py` は「似せない」「禁止」などの否定文だけではキャラ登場扱いにしない。

## 旧世代（未使用・撤去対象）
- 旧Gemini音声：`cloud_tts.py`/`gen_episode_cloud.py`/`reapply_ep01_gemini.py`/`regen_*`/`gemini_voice_audition_app.py`/`voice-auditions/`
- 旧パペット/PV：`puppet_motion_engine.py` 系 / `make_new_pv_video.py` / `13th-register-pv/`
- 中間物：`outputs/`（再生成可）
