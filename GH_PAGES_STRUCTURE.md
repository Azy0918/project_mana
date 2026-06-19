# gh-pages 構成見直しメモ

このブランチは GitHub Pages の公開ブランチであり、公開に必要な最小構成と、制作ソース保管が混在している。
当面は URL を壊さないことを優先し、段階的に整理する。

## 現在の主な構成

| パス | 現状 | 扱い |
|---|---|---|
| `13th-register-kamishibai/` | 第十三レジの正規公開プレイヤー | 公開の正 |
| `site/` | 旧または互換用プレイヤー。`13th-register-kamishibai/` と素材が重複 | 互換維持、将来統合候補 |
| `_source_12episodes/` | 12話シナリオ本文 | 制作ソースとして保持 |
| `PRODUCTION_SOURCE_INDEX.md` | 制作ソース索引 | 保持 |
| `anime-github-project/tools/` | 音声・画像・PV作成用スクリプトと制作CSV | 制作ツールとして保持 |
| `outputs/` | 生成結果、試聴音声、比較素材、再生成元など | 重い。必要分だけ保持、今後は原則Git追加しない |
| `13th-register-pv/` | 旧PV公開ページ | アーカイブ候補 |
| ルート `index.html` / `style.css` | 現在は別プロジェクトのページ | ポータル化またはアーカイブ候補 |
| `_worktrees/` | ローカル作業用 worktree | Git管理しない |

## 公開URLの正

第十三レジのスマホ確認・公開導線は下記を正とする。

- `https://azy0918.github.io/project_mana/13th-register-kamishibai/`

`site/` は現時点では壊さず残すが、今後の更新対象は `13th-register-kamishibai/` を優先する。

## 問題点

- ルート `index.html` が第十三レジではないため、リポジトリトップから目的のページへ辿りにくい。
- `site/` と `13th-register-kamishibai/` に同じ音声・画像・manifestが重複している。
- `outputs/` に大きなwavやpngが多数入り、公開ブランチが重くなっている。
- 確定素材、再生成元、試作、比較用、失敗生成の境界が曖昧。
- 一時生成の話者一覧など、Gitに入れる必要が薄いファイルが未追跡で残りやすい。

## 推奨する整理後の形

```text
/
├─ index.html                         # 第十三レジポータル
├─ .nojekyll
├─ PRODUCTION_SOURCE_INDEX.md
├─ GH_PAGES_STRUCTURE.md
├─ 13th-register-kamishibai/           # 公開の正
│  ├─ index.html
│  ├─ scene_manifest.json
│  ├─ visual_cut_plan.json
│  └─ assets/
├─ _source_12episodes/                 # 12話本文
├─ _production/                         # 将来作る制作設定置き場
│  ├─ character/
│  ├─ voice/
│  └─ prompts/
├─ _tools/                              # 将来 tools を整理するなら移動先
├─ _archive/                            # 旧PVや旧rootページ
└─ outputs/                             # 原則ローカル。Git追加は例外のみ
```

## 段階的な実行案

### Phase 1: 低リスク整理

- `GH_PAGES_STRUCTURE.md` を追加する。
- `.gitignore` に一時生成物を追加する。
- `13th-register-kamishibai/` を公開の正として明記する。
- 実ファイル移動はしない。

### Phase 2: ルート導線の整理

- ルート `index.html` を第十三レジポータルに差し替える。
- 旧ルートページは `_archive/duel-masters-research/` などへ退避する。
- `style.css` も旧ページ専用なら同じ場所へ退避する。

### Phase 3: 重複整理

- `site/` を互換ページとして残すか、`13th-register-kamishibai/` へリダイレクトする。
- `site/assets/` と `13th-register-kamishibai/assets/` の重複を減らす。
- ただし既存URL確認があるため、削除は最後にする。

### Phase 4: outputs 整理

- `outputs/` は基本的にGitへ追加しない。
- 公開に必要なものだけ `13th-register-kamishibai/assets/` にコピーする。
- 再生成元として残す価値があるものは `_archive/outputs/` または外部ストレージにまとめる。

## 当面のルール

- 新しい公開ページは `13th-register-kamishibai/` に集約する。
- 画像内に字幕・UI・時計・SNSボタンを描き込まない。UIはHTML側で重ねる。
- 12話本文と重要設定は GitHub に残す。
- 大量の生成途中ファイルは、明示的に必要な場合だけ Git に入れる。
- 削除や移動は、公開URLの確認後に行う。
