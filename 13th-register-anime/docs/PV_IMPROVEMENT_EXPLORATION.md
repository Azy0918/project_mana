# 第十三レジPV 改良探索メモ

作成日: 2026-06-15

## 現状

- 最新映像: `outputs/output_video/13th_register_pv_nise_new_images_sound.mp4`
- 尺: 約59.6秒
- 音声: AivisSpeech「にせ」ナレーション
- 画像: 新規アニメ調カット15枚
- 音響: 低音ドローン、雨、電子パルス、ヒット音、グリッチ音を合成済み

## いま一番効きそうな改善

### 1. 画面内テキストを減らす

現状は短いPV見出しを数カ所入れている。
アニメPV感を強めるなら、見出しをさらに減らして映像だけで見せる方がよい。

候補:

- 残す: 冒頭/ラストの「第十三レジ」
- 消す: 「午前二時三分」「夜だけ開くレジ」「未来からの返品」「なかったことにはしない」

メリット:

- 字幕っぽさが減る
- 映像素材の高級感が上がる

### 2. カット順をナレーションにもっと同期させる

現状は尺配分ベースで並べている。
ナレーションの意味単位に合わせて、絵の切り替えをさらに細かく調整すると予告編らしくなる。

重点:

- 「夜だけ開くレジ」直後にレジ正面
- 「未来が返品される」直後に袋/おにぎり
- 「人類の食糧危機」直後に未来ビジョン
- 「なかったことにはしない」直後にミナ操作/警告画面

### 3. 追加生成するなら「人物の手元」と「無人カット」

大きな人物カットは揃ってきた。
次に足りないのは、編集の呼吸を作る短い挿入カット。

追加候補:

- レジに置かれたレシート
- タクミの手がスキャナーを握る
- ミナの指がボタンを長押しする
- ホットコーヒーが注がれる
- 自動ドアが開く無人カット
- 空の棚と未来ビジョンの対比

### 4. 音響をもう一段PV寄りにする

現状のサウンドデザインは控えめ。
次は、次の3系統を足すとよい。

- 時計の秒針
- レジ起動時の短い上昇音
- ラストタイトル前の無音落とし

特に「一瞬無音にする」は無料でできて効果が大きい。

### 5. AnimateDiff / ComfyUIは別フェーズ

AnimateDiffは公式実装があり、既存のStable Diffusion系モデルに動きのモジュールを追加できる。
ただし、現環境には `torch` / `opencv` がなく、モデルもGB単位で必要になる。

今朝までに無理に入れるより、別枠で以下をやる方がよい。

- ComfyUIが残っているか確認
- GPU/VRAM確認
- AnimateDiff Evolved導入
- まず1カットだけ 2秒の動画化テスト

## 優先順位

1. 文字を減らした「映像重視版」を作る
2. 音響に秒針/無音落としを追加する
3. 手元・無人カットを5枚追加する
4. カット順をナレーション単位で再調整する
5. AnimateDiff/ComfyUIの導入可否を別途検証する

## 判断

Runway Gen-4が無料で使えないなら、最短で品質を上げる道は、
「画像枚数を増やす」「カット編集を詰める」「音響を映画予告寄りにする」の3つ。

本物のアニメーションに近づけるにはAnimateDiff系が候補だが、今のPC環境では即実行より準備が必要。

## 試作結果 2026-06-15 02:30台

### 試作A: 文字なし映像重視版

出力:

- `outputs/output_video/13th_register_pv_nise_cinematic_textless.mp4`
- `outputs/output_video/13th_register_pv_nise_cinematic_textless_sound.mp4`

内容:

- 追加のPV見出し文字を消した
- 元キービジュアル内のタイトルだけ残る
- サウンドデザイン版も作成

評価:

- セリフ字幕っぽさが減った
- 絵の高級感は少し上がる
- 物語の説明力はやや下がるが、ナレーションがあるので許容範囲

### 試作B: 音響再設計 v2

出力:

- `outputs/output_video/13th_register_pv_nise_cinematic_textless_sound_v2.mp4`
- `outputs/output_sound_design/13th_register_pv_sound_design_v2.wav`
- `outputs/output_sound_design/13th_register_pv_nise_mixed_v2.wav`

追加:

- 時計の秒針
- レジ出現/警告タイミングの一瞬の音量落とし
- レジ起動前の短い上昇音
- ラストタイトル前の短いブレス

評価:

- 無料でできる改善として効果が高い
- ナレーションを邪魔しないようダッキング済み
- ただし環境音は合成音なので、リアルなSE素材があればさらに良くなる

## 次の候補

1. 手元/無人カットをさらに5枚追加
2. ラストタイトル用に「文字なしキービジュアル」を生成し、タイトルを編集側で入れる
3. ComfyUI/AnimateDiff導入可否を別枠で検証
4. 無料SE素材を使えるサイトを確認し、ライセンス安全なものだけ採用

## 試作結果 2026-06-15 02:50台

### 試作C: 文字なしキービジュアル + 編集側タイトル

出力:

- `outputs/output_video/13th_register_pv_nise_title_control.mp4`
- `outputs/output_video/13th_register_pv_nise_title_control_sound_v2.mp4`
- `outputs/pv_image_assets_new/pv_key_visual_textless_v1.png`

内容:

- キービジュアル内の埋め込み文字をなくした
- 冒頭はタイトルなしで、キャラとレジを先に見せる構成にした
- ラストだけ編集側で `第十三レジ` を大きく表示
- ラストタイトルのフェードを短くして、可読性を上げた
- 音響は試作Bのv2を流用

評価:

- 冒頭のチープな文字感が消え、アニメPVらしさが上がった
- ラストだけタイトルを出すので、映像の余韻を壊しにくい
- タイトル位置は中央で読みやすいが、さらに作り込むなら専用ロゴ化が次の改善点

次にやるなら:

1. タイトルロゴを専用デザインにする
2. 手元、レジ画面、雨の外観などの短尺カットを5から8枚追加する
3. 2秒程度の瞬き・髪揺れ・レジ画面点滅を疑似アニメとして入れる

## 試作結果 2026-06-15 03:00台

### 試作D: 疑似アニメ効果 v1

出力:

- `outputs/output_video/13th_register_pv_nise_motion_v1.mp4`
- `outputs/output_video/13th_register_pv_nise_motion_v1_sound_v2.mp4`

内容:

- 雨の流れる線をフレームごとに追加
- レジ、警告、消失系カットに青い発光の揺らぎを追加
- 警告/消失カットにごく小さい画面揺れを追加
- `make_new_pv_video.py` に `--motion-effects` を追加し、通常版と動き版を切り替え可能にした

評価:

- 追加コストなしで静止画感が少し減る
- 雨とレジ発光は作品のトーンに合う
- 人物自体はまだ動かないため、完全なアニメというより「PVの動く紙芝居」の強化

次にやるなら:

1. 目パチ用にキャラ顔だけの差分画像を作る
2. レジ画面の表情差分を3枚作って点滅させる
3. 手元カットを増やして、人物の口や顔を無理に動かさずテンポを作る

## 試作結果 2026-06-15 03:10台

### 試作E: 専用タイトルロゴ処理 v1

出力:

- `outputs/output_video/13th_register_pv_nise_logo_v1.mp4`
- `outputs/output_video/13th_register_pv_nise_logo_v1_sound_v2.mp4`

内容:

- ラストの単純な発光文字を、線、縁取り、青い発光を持つロゴ風タイトルに変更
- 文字は画像生成に任せず、Pillowで直接描画して誤字を防止
- タイトル出現時にごく短いグリッチずれを追加
- 既存の `--motion-effects` と併用

評価:

- ラストの締めがPVらしくなった
- 生成画像内の文字より安定しており、修正もしやすい
- さらに上げるなら、作品専用のロゴデザインを別途1枚作る価値あり

### 試作F: 音響再設計 v3

出力:

- `outputs/output_sound_design/13th_register_pv_sound_design_v3.wav`
- `outputs/output_sound_design/13th_register_pv_nise_mixed_v3.wav`
- `outputs/output_video/13th_register_pv_nise_logo_v1_sound_v3.mp4`

内容:

- ロゴ出現タイミングに低いタイトルヒットを追加
- 短い電子的な余韻を追加
- v2音響を壊さず、別スクリプト `make_pv_sound_design_v3.py` として作成

検証:

- `python -m py_compile .\outputs\make_new_pv_video.py`
- `python -m py_compile .\outputs\make_pv_sound_design_v3.py`
- `python .\outputs\make_new_pv_video.py --help`
- `python .\outputs\make_pv_sound_design_v3.py --help`
- mixed v3 peak: 約 `0.956`

評価:

- ラストのタイトル感が少し強くなった
- 音割れは数値上なし
- 今のおすすめ版は `13th_register_pv_nise_logo_v1_sound_v3.mp4`

次にやるなら:

1. レジ画面の表情差分をコードで重ねる
2. 5枚程度の手元/商品/画面カットを追加生成する
3. 1分PVのナレーション間に合わせてカット順を再調整する

## 試作結果 2026-06-15 03:25台

### 試作G: 第十三レジの表情差分 v1

出力:

- `outputs/output_video/13th_register_pv_nise_register_face_v1.mp4`
- `outputs/output_video/13th_register_pv_nise_register_face_v1_sound_v3.mp4`

内容:

- `make_new_pv_video.py` に `--register-face` を追加
- 第十三レジの通常画面に、口変化とスキャン線を控えめに重ねた
- 最初は目の差分も試したが、既存の顔と二重に見えたため撤回
- 最終版は目を触らず、口とスキャン線だけにして破綻を減らした

検証:

- `python -m py_compile .\outputs\make_new_pv_video.py`
- `python .\outputs\make_new_pv_video.py --help`
- 代表フレーム:
  - `outputs/output_video/pv_register_face_v1_previews/preview_12.jpg`
  - `outputs/output_video/pv_register_face_v1_previews/preview_13.jpg`

評価:

- 破綻は少ない
- 効果は控えめで、単体では大幅改善ではない
- “レジが反応している”感じを少し足す補助効果としては採用可能
- 大きく効かせるなら、コード描画よりレジ画面専用の差分画像を3枚作る方がよい

次にやるなら:

1. レジ画面だけの専用差分画像を作る
2. 手元/商品/店内無人カットを増やす
3. ラストロゴ前に1秒の黒背景カードを挟む案を比較する

## 試作結果 2026-06-15 03:35台

### 試作H: 手元/商品/無人店内カット追加 v1

出力:

- `outputs/output_video/13th_register_pv_nise_cutaway_v1.mp4`
- `outputs/output_video/13th_register_pv_nise_cutaway_v1_sound_v3.mp4`

追加素材:

- `outputs/pv_image_assets_new/pv_cut_15_hand_scan.png`
- `outputs/pv_image_assets_new/pv_cut_16_empty_aisle.png`
- `outputs/pv_image_assets_new/pv_cut_17_alert_screen.png`
- `outputs/pv_image_assets_new/pv_cut_18_receipt_props.png`

内容:

- 手元スキャン、無人店内、警告画面、返金レシートの4カットを生成
- 既存の16シーンに短尺カットとして差し込み
- ロゴ、疑似アニメ効果、レジ口変化、音響v3と併用
- 1分尺は維持し、全シーンを自動圧縮

検証:

- `python -m py_compile .\outputs\make_new_pv_video.py .\outputs\make_pv_sound_design_v3.py`
- mixed v3 peak: 約 `0.956`
- 代表フレーム:
  - `outputs/output_video/pv_cutaway_v1_previews/preview_7_8.jpg`
  - `outputs/output_video/pv_cutaway_v1_previews/preview_15_9.jpg`
  - `outputs/output_video/pv_cutaway_v1_previews/preview_33_6.jpg`
  - `outputs/output_video/pv_cutaway_v1_previews/preview_48_9.jpg`

評価:

- 手元スキャンカットが特に効果的
- 無人店内カットは静かな間として使える
- 警告画面は既存カットより見栄えが良く、短い差し込みとして有効
- 返金レシートカットも物語の情報を補える
- 現時点のおすすめ版は `13th_register_pv_nise_cutaway_v1_sound_v3.mp4`

次にやるなら:

1. カット追加で少し詰まった可能性があるため、ナレーション単位で尺を再配分する
2. 手元スキャンをもう1カット増やして、レジ操作の連続性を作る
3. タイトル前に黒背景1秒案と現行ラストを比較する

## 試作結果 2026-06-15 10:10台

### 試作I: カット内アニメ効果 v2

出力:

- `outputs/output_video/13th_register_pv_nise_animated_v2.mp4`
- `outputs/output_video/13th_register_pv_nise_animated_v2_sound_v3.mp4`

内容:

- `make_new_pv_video.py` に `--advanced-animation` を追加
- 手元スキャンカットに、移動するスキャンビームと補助ラインを追加
- 警告画面カットに、赤いパルスと走査バンドを追加
- レシートカットに、印字が流れるような発光ラインを追加
- 無人店内カットに、照明ちらつきを追加
- 既存の雨、レジ発光、ロゴ、音響v3と併用

検証:

- `python -m py_compile .\outputs\make_new_pv_video.py`
- `python .\outputs\make_new_pv_video.py --help`
- mixed v3 peak: 約 `0.956`
- 代表フレーム:
  - `outputs/output_video/pv_animated_v2_previews/preview_15_4.jpg`
  - `outputs/output_video/pv_animated_v2_previews/preview_33_6.jpg`
  - `outputs/output_video/pv_animated_v2_previews/preview_48_9.jpg`

評価:

- 追加コストなしで、静止画切り替え感がさらに減った
- 手元スキャンと警告画面の効果が特に分かりやすい
- レシートは控えめだが、処理中の雰囲気が出る
- 現時点のおすすめ版は `13th_register_pv_nise_animated_v2_sound_v3.mp4`

次にやるなら:

1. スキャンビームが少し派手なので、必要なら弱め版を比較する
2. キャラクター顔の差分を作るなら、目パチよりカット追加の方が安全
3. ナレーションの節ごとにシーン尺を手調整する

## 試作結果 2026-06-15 16:40台

### 試作J: タクミ人物リアクション差分 v1

出力:

- `outputs/output_video/13th_register_pv_nise_human_motion_v1.mp4`
- `outputs/output_video/13th_register_pv_nise_human_motion_v1_sound_v3.mp4`

追加素材:

- `outputs/pv_image_assets_new/pv_cut_19_takumi_react_lookback.png`
- `outputs/pv_image_assets_new/pv_cut_20_takumi_react_blink.png`
- `outputs/pv_image_assets_new/pv_cut_21_takumi_react_mouth_open.png`

内容:

- `Scene` に `sequence` と `sequence_hold` を追加
- タクミのクローズアップカットだけ、複数画像を切り替えるキーフレーム方式に変更
- 口開き、まばたき、視線戻りの3差分を使用
- 既存のロゴ、手元スキャン、警告パルス、レシート印字、音響v3と併用

検証:

- `python -m py_compile .\outputs\make_new_pv_video.py`
- `python .\outputs\make_new_pv_video.py --help`
- mixed v3 peak: 約 `0.956`
- 代表フレーム:
  - `outputs/output_video/pv_human_motion_v1_previews/preview_17_6.jpg`
  - `outputs/output_video/pv_human_motion_v1_previews/preview_18_35.jpg`
  - `outputs/output_video/pv_human_motion_v1_previews/preview_18_55.jpg`

評価:

- 初めて「人が動いた」と感じられる版になった
- ただし瞬き・口開き・視線戻りの差分ごとに身体と背景が微妙にずれる
- タクミのカットでは違和感が目立つため、この方式は現状では不採用
- 人物差分を使う場合は、全身差分生成ではなく、元絵固定の目・口パーツ合成か、Live2D/骨格アニメ方式に寄せる

次にやるなら:

1. 人物は全フレーム生成ではなく、元絵を固定して目・口だけ動かす
2. ミナは派手に動かさず、カメラワークと手元カットで変化を出す
3. 人物カットを増やす場合は、別ポーズの新規カットとして使い、同一カット内で混ぜない

### 試作K: タクミ固定絵安定版 v1

出力:

- `outputs/output_video/13th_register_pv_nise_stable_body_v1.mp4`
- `outputs/output_video/13th_register_pv_nise_stable_body_v1_sound_v3.mp4`

内容:

- タクミのクローズアップで使っていた全フレーム人物差分シーケンスを停止
- 元のタクミ絵を固定し、ズーム・パン・既存の映像効果だけで動きを作る
- レジ表情、手元スキャン、警告パルス、レシート印字、音響v3は維持

検証:

- `python -m py_compile .\outputs\make_new_pv_video.py`
- `python .\outputs\make_new_pv_video.py --help`
- 代表フレーム:
  - `outputs/output_video/pv_stable_body_v1_previews/preview_17_60.jpg`
  - `outputs/output_video/pv_stable_body_v1_previews/preview_18_39.jpg`
  - `outputs/output_video/pv_stable_body_v1_previews/preview_19_22.jpg`

評価:

- 身体・服・背景のフレームごとのズレは解消
- 人物が動く量は減るが、違和感がなくPVとして安定
- 現時点のおすすめ版は `13th_register_pv_nise_stable_body_v1_sound_v3.mp4`

### 試作L: Live2D/After Effects風パーツ分解アニメ v1

出力:

- `outputs/output_video/13th_register_pv_puppet_v1.mp4`
- `outputs/output_video/13th_register_pv_puppet_v1_sound_v3.mp4`

内容:

- `make_new_pv_video.py` に `--puppet-animation` を追加
- 全身差分画像の切り替えは使わず、元フレームから人物領域を薄いフェザーマスクで切り出して微細に変形
- タクミの顔・手元、ミナの上半身・手元、二人カット、未来の会社員に呼吸・揺れを追加
- レジ表情、手元スキャン、警告パルス、レシート印字、音響v3は維持

検証:

- `python -m py_compile .\outputs\make_new_pv_video.py`
- `python .\outputs\make_new_pv_video.py --help`
- 代表フレーム:
  - `outputs/output_video/pv_puppet_v1_previews/preview_18_39_takumi.jpg`
  - `outputs/output_video/pv_puppet_v1_previews/preview_21_20_mina.jpg`
  - `outputs/output_video/pv_puppet_v1_previews/preview_25_20_pair.jpg`
  - `outputs/output_video/pv_puppet_v1_previews/preview_29_60_salaryman.jpg`

評価:

- 身体や背景が別画像へ跳ぶ問題は回避
- 動きは控えめだが、静止画PVより人物の生気が少し出る
- 現時点では `13th_register_pv_puppet_v1_sound_v3.mp4` を人物アニメ入りの推奨版とする
- 次に強化するなら、目・口・髪・腕を本当に透過パーツとして切り出し、個別レイヤー化する

### 試作M: Remotion全キャラ可動PV v3

出力:

- `outputs/output_video/13th_register_remotion_puppet_allcast_v3.mp4`
- `outputs/output_video/13th_register_remotion_puppet_allcast_v3_sound_v3.mp4`

内容:

- Remotion版 `NoSubtitleAnimePV` をLive2D/After Effects風に拡張
- タクミ、ミナ、未来の会社員、常連のおじいさんを全員登場させる終盤集合カットを追加
- 会話カットでは立ち絵に呼吸、上下動、微細な回転、口パク、瞬きを追加
- 第十三レジは発光パルス、グリッチ揺れ、スキャンラインで機械的な反応を強化
- `voice_drama.wav` を60秒へ切り、BGM/効果音と合成した音声入りMP4を生成
- 足元の矩形感を隠すため、前景の暗い床影を追加

検証:

- `.\node_modules\.bin\tsc.cmd --noEmit`
- Remotion render: `NoSubtitleAnimePV`
- `python .\outputs\make_remotion_dialogue_sound_design.py --duration-sec 60.05`
- 代表フレーム:
  - `outputs/output_video/remotion_puppet_allcast_v3_previews/preview_17_50_mina.jpg`
  - `outputs/output_video/remotion_puppet_allcast_v3_previews/preview_55_00_allcast.jpg`

評価:

- 全員が1分PV内に登場し、静止画PVより「人物がいる」感は上がった
- 既存立ち絵を疑似的に動かしているため、本物のLive2Dほど腕・髪・顔パーツは独立していない
- 現時点のRemotion系推奨版は `13th_register_remotion_puppet_allcast_v3_sound_v3.mp4`

### 試作N: 全キャラ台詞入りトレーラーPV v1

出力:

- `outputs/output_video/13th_register_remotion_trailer_allcast_v1.mp4`
- `outputs/output_video/13th_register_remotion_trailer_allcast_v1_sound_v3.mp4`

内容:

- 本編冒頭1分ではなく、PV用ナレーションと本編台詞を抜粋して60秒に再構成
- 使用音声:
  - PVナレーション: 午前2時3分、夜だけ開くレジ、だいじゅうさんレジ等
  - タクミ: 「はい……はい？」
  - ミナ: 「だいじゅうさんレジ。」
  - 第十三レジ: 「ただいま営業中。」、警告、人類生存率、未来へのメモ
  - 未来の会社員: 「2074年から来ました。」、上司のくだり
- `build_remotion_trailer_assets.py` で `trailer_voice.wav` と `trailerTimeline.ts` を生成
- `TrailerAnimePV` コンポジションを追加
- BGM/効果音は `make_remotion_dialogue_sound_design.py --voice trailer_voice.wav` で合成
- 常連のおじいさんは現台本ログに音声行がないため、今回は映像参加のみ

検証:

- `python -m py_compile .\outputs\build_remotion_trailer_assets.py`
- `python .\outputs\build_remotion_trailer_assets.py`
- `.\node_modules\.bin\tsc.cmd --noEmit`
- Remotion render: `TrailerAnimePV`
- mixed audio: duration `60.05s`, peak `0.98`, rms `0.1115`
- 代表フレーム:
  - `outputs/output_video/remotion_trailer_allcast_v1_previews/preview_12_takumi_mina.jpg`
  - `outputs/output_video/remotion_trailer_allcast_v1_previews/preview_21_future.jpg`
  - `outputs/output_video/remotion_trailer_allcast_v1_previews/preview_34_register.jpg`
  - `outputs/output_video/remotion_trailer_allcast_v1_previews/preview_55_allcast.jpg`

評価:

- 物語の宣伝PVとしては、冒頭1分そのままのv3よりこちらの方が内容が伝わりやすい
- 全員集合、レジの巨大カット、未来の会社員の台詞が入り、PVの情報密度が上がった
- 現時点の推奨版は `13th_register_remotion_trailer_allcast_v1_sound_v3.mp4`

### 試作O: 自動頭部パーツ分解 v2 不採用

出力:

- `outputs/output_video/13th_register_remotion_trailer_allcast_v2_parts.mp4`
- `outputs/output_video/13th_register_remotion_trailer_allcast_v2_parts_sound_v3.mp4`

内容:

- `prepare_remotion_character_parts.py` で元立ち絵から頭部と胴体を自動切り出し
- Remotion側で頭部だけを微細に回転・上下動させる方式を試した

評価:

- 自動楕円マスクが顔面に不自然な境界を作り、全員集合カットで特に違和感が出た
- この方式は不採用
- 採用版のソースは、安定している元立ち絵ベースの `TrailerAnimePV` に戻した
- 次に本当にLive2D風へ寄せるなら、自動楕円ではなく、人物ごとに頭・前髪・腕・胴体を手作業で透過切り出しする必要がある

### 試作P: 照明・前景モーション強化 v3 採用

出力:

- `outputs/output_video/13th_register_remotion_trailer_allcast_v3_lightmotion.mp4`
- `outputs/output_video/13th_register_remotion_trailer_allcast_v3_lightmotion_sound_v3.mp4`

内容:

- 自動頭部パーツ分解は不採用のまま、元立ち絵ベースで破綻しにくい方向に戻した
- 台詞イベントに合わせてスポット光、レジ発光リング、未来側の冷色発光を追加
- 前景棚影と床影をゆっくり動かし、画面全体の止まり感を減らした
- 会話、レジ警告、全員集合で照明の出方を変え、PVとしての場面転換を強めた
- 音声は `trailer_voice.wav` にBGM/効果音を合成したv3サウンドを使用

検証:

- `.\node_modules\.bin\tsc.cmd --noEmit`
- Remotion render: `TrailerAnimePV`
- mixed audio: duration `60.05s`, peak `0.98`, rms `0.1115`
- 代表フレーム:
  - `outputs/output_video/remotion_trailer_allcast_v3_lightmotion_previews/preview_12_mina.jpg`
  - `outputs/output_video/remotion_trailer_allcast_v3_lightmotion_previews/preview_21_future.jpg`
  - `outputs/output_video/remotion_trailer_allcast_v3_lightmotion_previews/preview_34_register.jpg`
  - `outputs/output_video/remotion_trailer_allcast_v3_lightmotion_previews/preview_55_allcast.jpg`
- コンタクトシート:
  - `outputs/output_video/13th_register_remotion_trailer_allcast_v3_contact_sheet.jpg`

評価:

- v2の顔マスク破綻を避けながら、v1よりも照明・前景・レジ反応で動きが増えた
- 本物のLive2Dパーツ分解ではないが、現素材で安全に見せられる採用版としてはv3が最も安定
- 現時点の推奨版は `13th_register_remotion_trailer_allcast_v3_lightmotion_sound_v3.mp4`
