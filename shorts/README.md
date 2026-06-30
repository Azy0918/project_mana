# ショート動画（YouTube Shorts / TikTok / Reels 用）

第3話「昨日に溶けるアイスクリーム」から、「溶けると昨日になるアイスを、
レジ袋で昨日と今日に分ける」一点だけを伝える縦型ショート（本編1〜3話への入口）。

## 生成方法
```
python anime-github-project/tools/build_ep03_short.py
```
- 構成: `shorts/ep03_short_yesterday_vanilla.json`（`line_ids` を本編 scene_manifest_ep03 から抽出）
- 音声: 既存 AivisSpeech クリップ `…/anime_clips/ep03_aivis/raw/*.wav` を連結（新規生成なし・BGMなし）
- 字幕: 本編 `build_episode_video.py` のスタイル/ヘルパーを import で流用（本編は無改変）
- 出力: `outputs/shorts/ep03_short_yesterday_vanilla.mp4`

## 仕様（検証済み）
縦9:16 / 1080x1920 / 30fps / H.264+AAC / 約31.7秒 / 字幕あり / BGMなし。
冒頭0秒台に「溶けると、昨日になります。」、終端に本編誘導エンドカード。

## 構成（11行・本編準拠の表記=エリ）
冷凍庫に昨日 → 日付管理なら白板 → 第十三レジ警告 → 袋お分けしますか → 今それ言う場面 →
昨日と今日で → **時間をレジ袋で分けるな！** → 理屈としては近い → **レジ袋が時空より強い！** →
袋代取るんですね → 袋は袋。
