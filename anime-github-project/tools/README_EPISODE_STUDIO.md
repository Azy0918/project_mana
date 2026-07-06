# エピソードスタジオ — セルフ紙芝居制作アプリ

台本アップロード → カット割り → 読み編集 → 音声生成 → プレイヤー反映 → YouTube動画 → 公開(push) を
**ブラウザだけ**(スマホ/PC)で完結させるローカルサーバー。Claudeのクレジット無しでエピソード制作を回せる。

## 起動(PC側・1回だけ)
```
tools\start_episode_studio.bat        (= python episode_studio_server.py, ポート8040)
```
- AivisSpeechは起動していなくてもOK(生成時に自動起動・劣化時は自動再起動)。
- PC本体では http://localhost:8040/ で開ける。

## スマホから使う(Tailscale)
1. PCに Tailscale をインストール → https://tailscale.com/download → 同じGoogleアカウント等でログイン。
2. スマホに Tailscale アプリ(App Store / Google Play)を入れて同じアカウントでログイン。
3. スマホのTailscaleアプリでPCの名前(例: `desktop-xxxx`)を確認し、ブラウザで
   `http://desktop-xxxx:8040/` または `http://100.x.y.z:8040/` を開く。ホーム画面に追加すると便利。
- Tailscaleは端末間の暗号化されたプライベート網なので外部には公開されない。
- さらに念のためPINを掛けるなら、起動前に `set STUDIO_PIN=好きな数字` (初回アクセス時に入力を求められる)。

## 画面の使い方
| タブ | できること |
|---|---|
| 📊 状態 | 全12話の行数/クリップ数/音声/動画の有無 |
| 📜 台本 | `話者：セリフ｜読み` 形式を貼り付け/ファイル選択→取り込み。`通常レジSE：ピッ。`行は直前行のスキャンSEに変換。行数が同じ再取込なら既存カット割りを継承、同一セリフのクリップは自動流用 |
| 🎙 行と読み | 行ごとに セリフ/読み をその場で編集(編集した行のクリップは自動破棄=要再生成)。🎙個別生成 / ▶試聴 / ✂カット開始の設定・解除 / ＋行挿入 / 🗑行削除(ID・クリップ自動繰り上げ) |
| 🖼 カット | カットごとの行範囲・タイトル編集・画像サムネイル・Codex向けファイル名と到着状況(🟢/🔴) |
| 🚀 生成と公開 | 未生成一括合成 / 全再合成 / プレイヤー反映(連結+タイミング+キャッシュバスト) / YouTube動画生成 / gh-pages公開(push) / 全体音声の試聴 |
| 🎨 Codex依頼 | 「この話の画像20枚をこのファイル名で」の依頼文を自動生成→コピーしてCodexへ |

## 画像の約束(Codex側)
- 保存先: `13th-register-kamishibai/assets/scenes/planned/`
- ファイル名: `epNN_vcNN_<説明>.png`(visual_cut_planのplannedImage優先。無ければ `epNN_vcNN_*.png` の最新を自動採用)
- 同名上書きなら反映操作は不要。プレイヤー反映/動画生成をスタジオから実行するだけ。

## 仕組み(既存パイプラインとの関係)
- 行データの正本 = `scene_manifest_epNN.json`(従来どおり)。スタジオはこれを直接編集する。
- 読みは manifest の `reading` を正とし、反映時にそのまま合成済みクリップと連結する
  (gen_episode_aivis.py のREADING_FIXES相当は取込時に自動適用、以後は手編集が優先)。
- クリップ置場: `C:\Users\qvf03\Documents\anime_clips\epNN_aivis\raw\epNN_vNNN.wav`(従来と同じ)。
- 反映で `index.html` の該当話 `?v=` を自動+1。
- 動画は `tools/build_episode_video.py` をそのまま呼ぶ(縦1080x1920)。
- AivisSpeech劣化バグ(連続合成~45回でpitchScale合成がConnectionReset)対策として、
  失敗時は AivisSpeech.exe / run.exe をkill→再起動→同じ行からリトライを内蔵。
- 公開は該当話のファイルだけを `git add → commit → push origin gh-pages`。

## 注意
- ジョブ(合成/反映/動画/公開)は同時に1つ。実行中は画面下にプログレスバーが出る。
- 台本の再取込は「置き換え」。行単位の微修正は🎙タブの直接編集の方が安全。
- ep01はファイル名が特殊(scene_manifest.json / ..._mina_mao.wav)だが対応済み。
