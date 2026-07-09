# 未開拓デッキ探索 進捗整理と新規展開案 (2026-07-09)

過去セッションの成果物(コミット履歴・srcモジュール群・data/cards.db の研究テーブル)を横断確認した結果の整理。

## これまでの進捗

### フェーズ1: 研究基盤MVP (v1.0, 5/29)
- Streamlitアプリ一式(カードDB、デッキ生成、評価、一人回し、進化探索、実戦ログ、リリース診断)。
- タグベースのデッキ生成・評価・未知性スコアが中心。

### フェーズ2: メタ情報収集と夜間研究ループ (5/31–6/3)
- `meta_decks`: 神ゲー攻略から現環境デッキ5件(火光レイド、火水レイドなど、ND第36弾)をレシピ付きで取り込み済み。
- `meta_research_seeds`: BEANS/X/手動メモ由来の研究seed 8件(黒緑ドンジャングル高レートレシピ、赤単ブランド対受け特化、白黒サバキZなど)。
- YouTube学習: 31本のトランスクリプトから `deck_knowledge` 31件、`matchup_insights` 16件、`video_learning_seeds` 38件を抽出。ただし抽出品質は粗く、game_plan は音声認識ノイズが多い。
- `research_theme.py` に研究テーマ7本を定義(黒緑ドンジャングル、黒緑TierSメタコントロール、赤白レイド、青単スコーラー、黒単デスザーク、白単サバキZ、アナカラーQQQX)。
- 夜間研究ランナー(`night_research_runner.py`)+ リモート研究ループアプリ(`remote_research_loop_app.py`)を6/3にデプロイ。
- 実テスト結果 (`final_test_matches` 17件): night黒緑ドンジャングル系候補は Tier S「火光レイド/ブランド」に全敗。4ターン目までに圧力をかけられず、ドンジャングルS7が dead card 化するのが敗因として記録されている。

### フェーズ3: 未開拓探索インフラ(実装済み・未実走)
- 全5178カードの効果特徴量 (`card_effect_features`) 構築済み。トリガー、ゾーン遷移、state_delta、制約破壊、勝利貢献などを構造化。
- 勝ち筋ルート探索 (`route_based_explorer.py`): 5系統のルート型を定義
  (ロック確定勝ち / ループ変換勝ち / 特殊勝利 / 山札切れ / 過剰打点)。
- `route_seed_generator` → `route_proof_searcher` → `route_deck_expander` → `route_deck_validator` の一連のパイプライン、`state_transition_model`、`win_condition_model`、`effect_graph_builder`、`special_combo_concepts`(状態変化/制約解除/価値増幅/ループ/特殊勝利)まで実装済み。

## 現状のギャップ

1. **ルート探索パイプラインが未実走**: `known_combos` 0件、`research_sessions` 0件、`generated_decks` 0件。インフラは揃ったが探索実績データがゼロ。
2. **タグとカードプールの不整合**: DBの `cards` は5178枚(公式スクレイプ)だが `card_tags` は0件。手動タグ付きは cards.csv の1250枚のみ。タグ依存の生成系(deck_builder/deck_explorer)は全カードプールで動かない。
3. **既知コンボの正解データがない**: `known_combos` が空のため、route_proof_searcher が「既知コンボを再発見できるか」という精度検証ができない。
4. **夜間研究レポートが揮発**: `data/reports/` はコミットされておらず、候補デッキの実体が残っていない(テスト結果のみDBに残存)。
5. **探索がメタカウンター寄り**: これまでの実走は黒緑ドンジャングル系のメタ対策構築が中心で、「未開拓アーキタイプ発見」という本来の目的にはまだ踏み込めていない。

## 新規展開案(優先順)

1. **既知コンボKBの初期投入とパイプライン精度検証**(最初にやる)
   - 現環境の既知コンボ(QQQX即死、グスタフループ、スコーラー、サバキZ など)を10–20件 `known_combos` に手動登録。
   - route_proof_searcher が既知コンボを再発見できるかで再現率を測り、探索器の信頼性を確認してから未知探索に進む。
2. **ルート探索の初回フルラン**
   - 5178枚プールで seed生成→証明探索→デッキ展開→検証を1周実行し、ルート型別の上位候補を `generated_decks` とレポート(リポジトリ管理下)に保存。
   - 候補の一次フィルタとして Tier S 仮想敵とのレースチェック(earliest_turn ベースで「4–5ターン目までに間に合うか」)を入れる。フェーズ2の全敗の教訓を反映。
3. **effect features からのタグ自動生成で全カードにタグ付与**
   - `card_effect_features` → タグ変換器を作り(`mana_tag_enricher` 拡張)、card_tags を5178枚分再構築。タグ系と特徴量系の探索を同一プールで動かす。
4. **効果グラフでのループ・閉路の機械的列挙**
   - `effect_graph_builder` + `state_transition_model` で「カードAの出力がカードBの入力条件になる」2–3枚の閉路を列挙し、novelty スコア順にランキング。未開拓コンボ発見の本丸。
5. **(低優先) YouTube抽出の品質改善**
   - matchup_insights の game_plan を要約構造化してから保存し、confidence しきい値で足切り。

## 次セッションの具体タスク

- [x] known_combos に既知コンボ10件以上を登録するスクリプト/CSVを作成
- [x] `python -m src.route_seed_generator` 系の実走とレポートの `data/reports/` 保存+コミット運用の決定
- [x] 再発見率(既知コンボのうち何件を探索器が自力で見つけるか)の計測

---

## 実走結果 (2026-07-09 同日追記)

### 実施内容

1. **既知コンボKB投入**: `src/known_combo_seed_data.py` で現環境の既知コンボ13件を `known_combos` に登録
   (青単スコーラー、QQQXループ、グスタフループ、ミラダンテ+ラフルル、必駆覇道、シャコガイル、J・イレブン、
   マッドネスカウンター、轟轟轟GG-0、B-零朱、ザビ・ミラ+ヴォルグ、ドンジャングル+デル・フィン、ヘブフォ絶十)。
   カード名は cards テーブルと完全一致を検証済み。
2. **再発見率計測ハーネス**: `src/route_rediscovery_checker.py` を新設。2つの指標を計測:
   - グローバル指標: 全勝利条件の探索上位ルートに既知コンボのコアカードが同居するか
   - アンカー指標: コアカード1枚を起点固定した探索(`search_route_proofs(anchor_card_name=...)` を追加)で相方を拾えるか
   - レポート: `data/reports/rediscovery/`
3. **探索器の修正**: エネイブラー(踏み倒し/展開/再利用)のプール別枠追加、
   ロック勝ちルートで負値permission(例: デル・フィンの `cast_permission:-2`)をhelper加点対象にする意味論修正
4. **フルラン**: route_seed_generator / route_proof_searcher --all / route_based_explorer(全5ルート型)を実行。
   `generated_decks` に10件保存、レポートは `data/reports/` にコミット。

### 計測結果

| 指標 | 結果 |
| --- | --- |
| グローバル再発見率 | 1〜2/13 (約8〜15%)。単カード特殊勝利(シャコガイル、J・イレブン)のみ |
| アンカー再発見率 | 0/9。2枚コンボの相方は一度も上位に浮上せず |

試した改良(汎用チェーンボーナス)はむしろ悪化(15%→0%)したため撤回。

### 根本原因の特定: 特徴量 state_delta の過剰付与

再発見失敗はスコアリングではなく**入力データの識別力不足**が原因。

- `resource_loop` が全5178枚中 36% に付与(本来は数十枚レベルの希少状態のはず)
- `opponent_action_lock` が 10%(497枚)に付与。ドロー呪文のエターナル・ブレインにすら `opponent_action_lock:2` が付く
- `win_progress` 30%、`damage_pressure` 60%
- `creature_deploy` シグナルはほぼ全カードに付き、リンク判定に使えない
- 一方で “必駆”蛮触礼亞 の踏み倒しに `cost_bypass` が付かないなど、肝心なカードで抽出漏れ

この状態ではどんな探索アルゴリズムでも既知コンボと汎用カードを区別できない。

### 次の最優先タスク(優先順)

1. **card_effect_feature_builder の state_delta 抽出精度の改善**(本丸)
   - `resource_loop` / `opponent_action_lock` / `win_progress` の付与条件を厳格化(パターン監査)
   - 踏み倒し(「コストを支払わずに」「出す」系)の `cost_bypass` 抽出漏れ修正
   - 改善のたびに `python -m src.route_rediscovery_checker` を回帰テストとして実行し、
     アンカー再発見率が上がることを確認する(計測基盤は今回整備済み)
2. 特徴量改善後、`card_relation_discoverer` の関係ルール(cost_bypass→needs_payoff等)を
   `_score_route` のチェーンボーナスとして再導入
3. route_based_explorer の重複出力(A/BとB/Aの同一ペア)のdedupe
4. 生成された10デッキ(特に ウルフェウス+セフィア・パルテノンのループ、ジョリー・ザ・ジョニー特殊勝利)の実戦検証

### 成果物

- `src/known_combo_seed_data.py`(既知コンボseed 13件+名寄せ検証)
- `src/route_rediscovery_checker.py`(再発見率の回帰計測ハーネス)
- `src/route_proof_searcher.py`(アンカー探索対応、エネイブラープール枠、ロック意味論修正)
- `data/reports/rediscovery/`、`data/reports/route_*`、`data/reports/route_based_exploration_run.json`
- `generated_decks` にルート探索由来の10デッキ(cards.db内)

---

## 特徴量抽出の精度改善 (2026-07-09 第2ラウンド)

### 修正内容 (effect_semantics / state_transition_model / effect_graph_builder / card_effect_feature_builder)

1. **主語判定の導入**: カードテキストを文単位に分割し、「相手」を含む文でのみ相手への
   行動制限(唱えられない/召喚できない/攻撃できない/能力無視)を `opponent_action_lock` に付与。
   駱駝の御輿の「攻撃できない。」(自分側デメリット)のような誤検出を解消。
2. **防御置換と特殊勝利の区別**: 「相手がゲームに勝つ時、かわりに〜」(完全防御革命、フルメタル・レモン)を
   自分の特殊勝利から除外する `has_self_win_text` を新設し、semantics/builder/searcher の3箇所に適用。
3. **追加ターン禁止の除外**: 「誰もターンを追加できず〜」(侵略者ランドヘッド)を追加ターン持ちと
   誤検出していた問題を `has_extra_turn_text`(否定形対応)で解消。
4. **コメント自己汚染の除去**: 生成コメント文(「追加ターンなど終端効果の候補があります」)が
   キーワードhaystackに混入して全terminal持ちにturn_countが付くループを遮断。
5. **cost_bypassの抽出漏れ修正**: 「(手札|マナ|墓地|山札)から〜バトルゾーンに出す」構文の正規表現を追加。
   必駆蛮触礼亞・ヘブンズ・フォース・グスタフに cost_bypass が付くようになった。
6. **resource_loopの厳格化**: 墓地肥やし(graveyard_plus)からの付与を廃止、recursionは+1に減量、
   loop_candidateの「唱えてもよい」を自己再利用文脈(「唱えた後」「もう一度唱え」等)に限定。
   「相手のクリーチャーを手札に戻す」(除去バウンス)をrecursion扱いしない主語判定も追加。
7. **その他**: attack_readyの「アンタップ」単体発火を廃止、creature_deployを「出す/出し」形のみに限定
   (cip誘発「出た時」の誤検出解消)、山札破壊圧は「相手/自身の山札」文のみに限定。
8. route_based_explorer: A/B・B/A重複seedと同名別刷りペアのdedupe。

### 状態分布の改善 (全5178枚中の付与率)

| 状態 | 修正前 | 修正後 |
| --- | --- | --- |
| resource_loop | 36% | 15.5% |
| opponent_action_lock | 10% | 5.1% |
| win_progress | 30% | **0.8% (41枚)** |
| alternate_win_progress | 0.4% | 0.4% (21枚、偽陽性除去済み) |
| turn_count | 5% | **0.4% (20枚)** |
| opponent_deck_pressure | 18% | 3.1% |

探索出力も質的に改善: alternate_effect_winルートの上位が本物の特殊勝利カード
(ケロヨン・カルテット、ザ・ユニバース・ゲート、シャコガイル+ジョリー・ザ・ジョニー、QQQX)で
構成されるようになった。

### 新しい回帰指標: 相方順位

miss/full二値では改善が見えないため、「アンカー(コア1枚)+全カードのペアスコア総当たりで、
真の相方が何位に来るか」を `check_partner_ranks` として計測に追加。

ベースライン (2026-07-09時点、母数約4856枚):

| コンボ | 相方順位 |
| --- | --- |
| ドンジャングルS7 → デル・フィン | 224 |
| バクアドルガン → バイケン | 367 |
| オブザ08号 → QQQX | 442 |
| 絶十 → ヘブンズ・フォース | 783 |
| グスタフ → 落城の計 | 946 |
| 必駆 → 覇道 | 2669 |
| 必駆 → B-零朱レイド | 2853 |
| ミラダンテXII → ラフルル | 2979 |
| ザビ・ミラ → ヴォルグ・サンダー | 計測不能(超次元カードはプール除外) |

**中央値: 946位**。状態加算スコアだけでは相方は上位に来ない(ビーム探索の採用圏は〜100位)。

### 結論と次のマイルストーン

特徴量の精度は大幅に改善したが、2枚コンボの再発見には
「**カード間のメカニズム参照の解決**」が必要と確定:

- 革命チェンジ(ミラダンテ/ラフルル) ⇔ チェンジ元の攻撃
- 必駆「ビートジョッキーを出す」 ⇔ 覇道の種族・コスト条件
- 無月の門 ⇔ 魔導具、NEO進化 ⇔ 進化元、超次元 ⇔ サイキック

次セッションのタスク:
1. テキストから「何を出せるか(種族/文明/コスト上限/ゾーン)」「何に出されられるか」を
   構造化する参照抽出器を作り、ProofCardNodeに載せる
2. `_score_route` に参照一致ボーナス(A_deploys ∩ B_deployable)を導入し、
   相方順位の中央値946→大幅短縮を狙う(回帰: `python -m src.route_rediscovery_checker`)
3. 超次元・サイキックカードのプール除外方針の再検討(ザビ・ミラ+ヴォルグが計測不能)
4. 改善後にルート探索フルラン→生成デッキの実戦検証へ
