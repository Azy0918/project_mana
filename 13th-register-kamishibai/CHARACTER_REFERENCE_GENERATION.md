# キャラ参照画像生成

## 目的

20カット x 12話の画像生成で、同一キャラクター・同一機体を維持する。

各カットは次の3点を必ず併用する。

1. `imagePrompt` または `prompt` の場面指示
2. `characterReferenceImages` の参照画像
3. `characterReferenceInstruction` の固定ルール

キャラ表だけを見る運用ではなく、生成ジョブごとに参照画像を入力する。

## 正本

- キャラ設定と参照画像: `assets/character_reference.json`
- 生成向け参照画像マップ: `assets/character_generation_refs.json`
- 各発話・各カットの参照割当:
  - `scene_manifest*.json`
  - `visual_cut_plan*.json`
- 生成ジョブ一覧: `assets/generation_jobs/character_reference_jobs.jsonl`

## 更新コマンド

```powershell
python 13th-register-kamishibai/tools/apply_character_references.py
```

設定だけ確認する場合:

```powershell
python 13th-register-kamishibai/tools/apply_character_references.py --dry-run
```

## ComfyUI / IP-Adapter 接続

各生成ジョブで次を行う。

1. `imagePrompt` をテキスト条件として使う。
2. `characterReferenceImages[].path` の画像を読み込む。
3. 登場人物ごとにIP-AdapterまたはReference Onlyへ接続する。
4. ポーズが必要なカットはOpenPose / Depth / Lineartを別途追加する。
5. 複数人物カットは、人物ごとにリージョンまたはマスクを分ける。

参照画像は「同じ人物・同じ服・同じ機体のデザイン」を維持するために使う。
キャラ表の白背景、余白、文字、説明レイアウトは画面内へ写さない。

## LoRA の扱い

現段階ではLoRAより参照画像方式を優先する。

- タクミ / ミナ / 第十三レジ: 参照画像を必ず使う。
- 汗田 / 座木山 / 唐沢: 登場カットで参照画像を使う。
- LoRAは、安定した教師画像を各キャラ10〜30枚以上用意できた段階で追加する。

LoRAを追加する場合も、複数人物カットの位置・ポーズ・衣装固定には
IP-AdapterやControlNetを併用する。
