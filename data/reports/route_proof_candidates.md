# route_proof_searcher 候補

勝利条件モデルから逆算した、勝利証明型ルート候補です。
現段階では完全なルール証明ではなく、状態変換連鎖の仮説を機械的に並べるための土台です。

## サマリー

- win_condition: all
- candidate_count: 48
- best_proof_score: 100
- missing_state: なし

## 候補一覧

| deck_name | route_type | proof_score | total_cost | depth | route_seed_cards | missing_states | required_support_roles |
| --- | --- | ---: | ---: | ---: | --- | --- | --- |
| proof_based direct_attack_win #1 | direct_attack_win | 69 | 7 | 1 | 無双竜機ボルバルザーク | attack_permission | 打点形成 |
| proof_based direct_attack_win #2 | direct_attack_win | 67 | 1 | 1 | ベイB パオパオ | attack_permission | 打点形成 |
| proof_based direct_attack_win #3 | direct_attack_win | 67 | 3 | 2 | ベイB パオパオ / こたつむり | attack_permission | 打点形成 |
| proof_based direct_attack_win #4 | direct_attack_win | 67 | 7 | 2 | ベイB パオパオ / ザ・ユニバース・ゲート | attack_permission | 打点形成 |
| proof_based direct_attack_win #5 | direct_attack_win | 67 | 3 | 2 | ベイB パオパオ / 奇石 ミクセル/ジャミング・チャフ | attack_permission | 打点形成 |
| proof_based direct_attack_win #6 | direct_attack_win | 67 | 3 | 2 | ベイB パオパオ / 制御の翼 オリオティス | attack_permission | 打点形成 |
| proof_based direct_attack_win #7 | direct_attack_win | 67 | 7 | 2 | D2B バブール / ザ・ユニバース・ゲート | attack_permission | 打点形成 |
| proof_based direct_attack_win #8 | direct_attack_win | 67 | 3 | 2 | こたつむり / ベイB パオパオ | attack_permission | 打点形成 |
| proof_based damage_overflow_win #1 | damage_overflow_win | 100 | 4 | 1 | 運命の選択 |  |  |
| proof_based damage_overflow_win #2 | damage_overflow_win | 100 | 1 | 1 | ベイB パオパオ |  |  |
| proof_based damage_overflow_win #3 | damage_overflow_win | 100 | 4 | 1 | 眠りの森のメイ様 |  |  |
| proof_based damage_overflow_win #4 | damage_overflow_win | 100 | 8 | 2 | 運命の選択 / 機真装甲ヴァルドリル |  |  |
| proof_based damage_overflow_win #5 | damage_overflow_win | 100 | 7 | 2 | 運命の選択 / 風の1号 ハムカツマン |  |  |
| proof_based damage_overflow_win #6 | damage_overflow_win | 100 | 6 | 2 | 運命の選択 / 漆黒の猛虎 チェイサー |  |  |
| proof_based damage_overflow_win #7 | damage_overflow_win | 100 | 6 | 2 | 運命の選択 / 爆冒険 キルホルマン |  |  |
| proof_based damage_overflow_win #8 | damage_overflow_win | 100 | 6 | 2 | 運命の選択 / 超速レーサー・パラリラ |  |  |
| proof_based alternate_effect_win #1 | alternate_effect_win | 84 | 6 | 2 | ケロヨン・カルテット / チェレンコ |  |  |
| proof_based alternate_effect_win #2 | alternate_effect_win | 84 | 6 | 2 | ケロヨン・カルテット / セツナノ裁徒 |  |  |
| proof_based alternate_effect_win #3 | alternate_effect_win | 84 | 6 | 2 | チェレンコ / ケロヨン・カルテット |  |  |
| proof_based alternate_effect_win #4 | alternate_effect_win | 83 | 7 | 2 | ザ・ユニバース・ゲート / ベイB パオパオ |  |  |
| proof_based alternate_effect_win #5 | alternate_effect_win | 83 | 7 | 2 | ザ・ユニバース・ゲート / ベイB ポレポレ |  |  |
| proof_based alternate_effect_win #6 | alternate_effect_win | 83 | 7 | 2 | ザ・ユニバース・ゲート / ベイB ソーター |  |  |
| proof_based alternate_effect_win #7 | alternate_effect_win | 83 | 7 | 2 | ザ・ユニバース・ゲート / ベイB クッジャ |  |  |
| proof_based alternate_effect_win #8 | alternate_effect_win | 83 | 7 | 2 | ザ・ユニバース・ゲート / D2B バブール |  |  |
| proof_based opponent_deckout_win #1 | opponent_deckout_win | 86 | 4 | 2 | 栄光の翼 バロンアルデ / 天斬の悪魔龍 ジュランデス |  |  |
| proof_based opponent_deckout_win #2 | opponent_deckout_win | 86 | 4 | 2 | 栄光の翼 バロンアルデ / グレイト“S-駆” |  |  |
| proof_based opponent_deckout_win #3 | opponent_deckout_win | 86 | 4 | 2 | 栄光の翼 バロンアルデ / Dの揺籠 メリーボーイラウンド |  |  |
| proof_based opponent_deckout_win #4 | opponent_deckout_win | 86 | 4 | 2 | 地の学び 至脚 / 天斬の悪魔龍 ジュランデス |  |  |
| proof_based opponent_deckout_win #5 | opponent_deckout_win | 86 | 4 | 2 | 地の学び 至脚 / グレイト“S-駆” |  |  |
| proof_based opponent_deckout_win #6 | opponent_deckout_win | 86 | 4 | 2 | 地の学び 至脚 / Dの揺籠 メリーボーイラウンド |  |  |

## 上位候補詳細

## 1. proof_based direct_attack_win #1

- candidate_origin: proof_based
- route_type: direct_attack_win
- proof_score: 69
- route_seed_cards: 無双竜機ボルバルザーク
- total_cost: 7
- missing_states: attack_permission
- required_support_roles: 打点形成

### state_chain
無双竜機ボルバルザーク (action_window:+2 / alternate_win_progress:+3 / board:+1 / damage_pressure:+4 / extra_turn:+1 / loop_output_to_win:+1 / tempo:+4 / terminal_win:+1 / turn_count:+2 / win_progress:+4) -> direct_attack_win (action_window:+2 / alternate_win_progress:+3 / board:+1 / damage_pressure:+4 / extra_turn:+1 / loop_output_to_win:+1 / tempo:+4 / terminal_win:+1 / turn_count:+2 / win_progress:+4)

### produced_states
{"action_window": 2, "alternate_win_progress": 3, "board": 1, "damage_pressure": 4, "extra_turn": 1, "loop_output_to_win": 1, "tempo": 4, "terminal_win": 1, "turn_count": 2, "win_progress": 4}

### proof_comment
direct_attack_winへの状態変換候補です。seed=無双竜機ボルバルザーク。作れている状態は action_window:+2 / alternate_win_progress:+3 / board:+1 / damage_pressure:+4 / extra_turn:+1 / loop_output_to_win:+1 / tempo:+4 / terminal_win:+1 / turn_count:+2 / win_progress:+4。不足は attack_permission。次は 打点形成 を探します。

## 2. proof_based direct_attack_win #2

- candidate_origin: proof_based
- route_type: direct_attack_win
- proof_score: 67
- route_seed_cards: ベイB パオパオ
- total_cost: 1
- missing_states: attack_permission
- required_support_roles: 打点形成

### state_chain
ベイB パオパオ (board:+1 / damage_pressure:+3 / graveyard:+1 / hand:+1 / loop_output_to_win:+1 / mana:+1 / opponent_deck_pressure:+1 / repeated_attack:+1 / resource_loop:+2 / tempo:+1) -> direct_attack_win (board:+1 / damage_pressure:+3 / graveyard:+1 / hand:+1 / loop_output_to_win:+1 / mana:+1 / opponent_deck_pressure:+1 / repeated_attack:+1 / resource_loop:+2 / tempo:+1)

### produced_states
{"board": 1, "damage_pressure": 3, "graveyard": 1, "hand": 1, "loop_output_to_win": 1, "mana": 1, "opponent_deck_pressure": 1, "repeated_attack": 1, "resource_loop": 2, "tempo": 1}

### proof_comment
direct_attack_winへの状態変換候補です。seed=ベイB パオパオ。作れている状態は board:+1 / damage_pressure:+3 / graveyard:+1 / hand:+1 / loop_output_to_win:+1 / mana:+1 / opponent_deck_pressure:+1 / repeated_attack:+1 / resource_loop:+2 / tempo:+1。不足は attack_permission。次は 打点形成 を探します。

## 3. proof_based direct_attack_win #3

- candidate_origin: proof_based
- route_type: direct_attack_win
- proof_score: 67
- route_seed_cards: ベイB パオパオ / こたつむり
- total_cost: 3
- missing_states: attack_permission
- required_support_roles: 打点形成

### state_chain
ベイB パオパオ (board:+1 / damage_pressure:+3 / graveyard:+1 / hand:+1 / loop_output_to_win:+1 / mana:+1 / opponent_deck_pressure:+1 / repeated_attack:+1 / resource_loop:+2 / tempo:+1) -> こたつむり (attack_permission:-2 / board:+1 / damage_pressure:+3 / defense:+1 / loop_output_to_win:+1 / opponent_action_lock:+1 / repeated_attack:+1) -> direct_attack_win (attack_permission:-2 / board:+2 / damage_pressure:+6 / defense:+1 / graveyard:+1 / hand:+1 / loop_output_to_win:+2 / mana:+1 / opponent_action_lock:+1 / opponent_deck_pressure:+1 / repeated_attack:+2 / resource_loop:+2 / tempo:+1)

### produced_states
{"attack_permission": -2, "board": 2, "damage_pressure": 6, "defense": 1, "graveyard": 1, "hand": 1, "loop_output_to_win": 2, "mana": 1, "opponent_action_lock": 1, "opponent_deck_pressure": 1, "repeated_attack": 2, "resource_loop": 2, "tempo": 1}

### proof_comment
direct_attack_winへの状態変換候補です。seed=ベイB パオパオ / こたつむり。作れている状態は attack_permission:-2 / board:+2 / damage_pressure:+6 / defense:+1 / graveyard:+1 / hand:+1 / loop_output_to_win:+2 / mana:+1 / opponent_action_lock:+1 / opponent_deck_pressure:+1 / repeated_attack:+2 / resource_loop:+2 / tempo:+1。不足は attack_permission。次は 打点形成 を探します。

## 4. proof_based direct_attack_win #4

- candidate_origin: proof_based
- route_type: direct_attack_win
- proof_score: 67
- route_seed_cards: ベイB パオパオ / ザ・ユニバース・ゲート
- total_cost: 7
- missing_states: attack_permission
- required_support_roles: 打点形成

### state_chain
resource_loop(existing) -> ベイB パオパオ (board:+1 / damage_pressure:+3 / graveyard:+1 / hand:+1 / loop_output_to_win:+1 / mana:+1 / opponent_deck_pressure:+1 / repeated_attack:+1 / resource_loop:+2 / tempo:+1) -> ザ・ユニバース・ゲート (action_window:+2 / alternate_win_progress:+3 / extra_turn:+1 / graveyard:+1 / loop_output_to_win:+1 / opponent_deck_pressure:+1 / resource_loop:+1 / tempo:+3 / terminal_win:+1 / turn_count:+2 / win_progress:+4) -> direct_attack_win (action_window:+2 / alternate_win_progress:+3 / board:+1 / damage_pressure:+3 / extra_turn:+1 / graveyard:+2 / hand:+1 / loop_output_to_win:+2 / mana:+1 / opponent_deck_pressure:+2 / repeated_attack:+1 / resource_loop:+3 / tempo:+4 / terminal_win:+1 / turn_count:+2 / win_progress:+4)

### produced_states
{"action_window": 2, "alternate_win_progress": 3, "board": 1, "damage_pressure": 3, "extra_turn": 1, "graveyard": 2, "hand": 1, "loop_output_to_win": 2, "mana": 1, "opponent_deck_pressure": 2, "repeated_attack": 1, "resource_loop": 3, "tempo": 4, "terminal_win": 1, "turn_count": 2, "win_progress": 4}

### proof_comment
direct_attack_winへの状態変換候補です。seed=ベイB パオパオ / ザ・ユニバース・ゲート。作れている状態は action_window:+2 / alternate_win_progress:+3 / board:+1 / damage_pressure:+3 / extra_turn:+1 / graveyard:+2 / hand:+1 / loop_output_to_win:+2 / mana:+1 / opponent_deck_pressure:+2 / repeated_attack:+1 / resource_loop:+3 / tempo:+4 / terminal_win:+1 / turn_count:+2 / win_progress:+4。不足は attack_permission。次は 打点形成 を探します。

## 5. proof_based direct_attack_win #5

- candidate_origin: proof_based
- route_type: direct_attack_win
- proof_score: 67
- route_seed_cards: ベイB パオパオ / 奇石 ミクセル/ジャミング・チャフ
- total_cost: 3
- missing_states: attack_permission
- required_support_roles: 打点形成

### state_chain
resource_loop(existing) -> ベイB パオパオ (board:+1 / damage_pressure:+3 / graveyard:+1 / hand:+1 / loop_output_to_win:+1 / mana:+1 / opponent_deck_pressure:+1 / repeated_attack:+1 / resource_loop:+2 / tempo:+1) -> 奇石 ミクセル/ジャミング・チャフ (board:+1 / cast_permission:-2 / damage_pressure:+1 / disruption:+2 / loop_output_to_win:+1 / opponent_action_lock:+2 / opponent_deck_pressure:+1 / resource_loop:+1) -> direct_attack_win (board:+2 / cast_permission:-2 / damage_pressure:+4 / disruption:+2 / graveyard:+1 / hand:+1 / loop_output_to_win:+2 / mana:+1 / opponent_action_lock:+2 / opponent_deck_pressure:+2 / repeated_attack:+1 / resource_loop:+3 / tempo:+1)

### produced_states
{"board": 2, "cast_permission": -2, "damage_pressure": 4, "disruption": 2, "graveyard": 1, "hand": 1, "loop_output_to_win": 2, "mana": 1, "opponent_action_lock": 2, "opponent_deck_pressure": 2, "repeated_attack": 1, "resource_loop": 3, "tempo": 1}

### proof_comment
direct_attack_winへの状態変換候補です。seed=ベイB パオパオ / 奇石 ミクセル/ジャミング・チャフ。作れている状態は board:+2 / cast_permission:-2 / damage_pressure:+4 / disruption:+2 / graveyard:+1 / hand:+1 / loop_output_to_win:+2 / mana:+1 / opponent_action_lock:+2 / opponent_deck_pressure:+2 / repeated_attack:+1 / resource_loop:+3 / tempo:+1。不足は attack_permission。次は 打点形成 を探します。

## 6. proof_based direct_attack_win #6

- candidate_origin: proof_based
- route_type: direct_attack_win
- proof_score: 67
- route_seed_cards: ベイB パオパオ / 制御の翼 オリオティス
- total_cost: 3
- missing_states: attack_permission
- required_support_roles: 打点形成

### state_chain
resource_loop(existing) -> ベイB パオパオ (board:+1 / damage_pressure:+3 / graveyard:+1 / hand:+1 / loop_output_to_win:+1 / mana:+1 / opponent_deck_pressure:+1 / repeated_attack:+1 / resource_loop:+2 / tempo:+1) -> 制御の翼 オリオティス (attack_permission:-2 / board:+1 / damage_pressure:+1 / defense:+1 / loop_output_to_win:+1 / opponent_action_lock:+1 / opponent_deck_pressure:+1 / resource_loop:+1) -> direct_attack_win (attack_permission:-2 / board:+2 / damage_pressure:+4 / defense:+1 / graveyard:+1 / hand:+1 / loop_output_to_win:+2 / mana:+1 / opponent_action_lock:+1 / opponent_deck_pressure:+2 / repeated_attack:+1 / resource_loop:+3 / tempo:+1)

### produced_states
{"attack_permission": -2, "board": 2, "damage_pressure": 4, "defense": 1, "graveyard": 1, "hand": 1, "loop_output_to_win": 2, "mana": 1, "opponent_action_lock": 1, "opponent_deck_pressure": 2, "repeated_attack": 1, "resource_loop": 3, "tempo": 1}

### proof_comment
direct_attack_winへの状態変換候補です。seed=ベイB パオパオ / 制御の翼 オリオティス。作れている状態は attack_permission:-2 / board:+2 / damage_pressure:+4 / defense:+1 / graveyard:+1 / hand:+1 / loop_output_to_win:+2 / mana:+1 / opponent_action_lock:+1 / opponent_deck_pressure:+2 / repeated_attack:+1 / resource_loop:+3 / tempo:+1。不足は attack_permission。次は 打点形成 を探します。

## 7. proof_based direct_attack_win #7

- candidate_origin: proof_based
- route_type: direct_attack_win
- proof_score: 67
- route_seed_cards: D2B バブール / ザ・ユニバース・ゲート
- total_cost: 7
- missing_states: attack_permission
- required_support_roles: 打点形成

### state_chain
resource_loop(existing) -> D2B バブール (board:+1 / damage_pressure:+3 / graveyard:+1 / hand:+1 / loop_output_to_win:+1 / opponent_deck_pressure:+1 / repeated_attack:+1) -> ザ・ユニバース・ゲート (action_window:+2 / alternate_win_progress:+3 / extra_turn:+1 / graveyard:+1 / loop_output_to_win:+1 / opponent_deck_pressure:+1 / resource_loop:+1 / tempo:+3 / terminal_win:+1 / turn_count:+2 / win_progress:+4) -> direct_attack_win (action_window:+2 / alternate_win_progress:+3 / board:+1 / damage_pressure:+3 / extra_turn:+1 / graveyard:+2 / hand:+1 / loop_output_to_win:+2 / opponent_deck_pressure:+2 / repeated_attack:+1 / resource_loop:+1 / tempo:+3 / terminal_win:+1 / turn_count:+2 / win_progress:+4)

### produced_states
{"action_window": 2, "alternate_win_progress": 3, "board": 1, "damage_pressure": 3, "extra_turn": 1, "graveyard": 2, "hand": 1, "loop_output_to_win": 2, "opponent_deck_pressure": 2, "repeated_attack": 1, "resource_loop": 1, "tempo": 3, "terminal_win": 1, "turn_count": 2, "win_progress": 4}

### proof_comment
direct_attack_winへの状態変換候補です。seed=D2B バブール / ザ・ユニバース・ゲート。作れている状態は action_window:+2 / alternate_win_progress:+3 / board:+1 / damage_pressure:+3 / extra_turn:+1 / graveyard:+2 / hand:+1 / loop_output_to_win:+2 / opponent_deck_pressure:+2 / repeated_attack:+1 / resource_loop:+1 / tempo:+3 / terminal_win:+1 / turn_count:+2 / win_progress:+4。不足は attack_permission。次は 打点形成 を探します。

## 8. proof_based direct_attack_win #8

- candidate_origin: proof_based
- route_type: direct_attack_win
- proof_score: 67
- route_seed_cards: こたつむり / ベイB パオパオ
- total_cost: 3
- missing_states: attack_permission
- required_support_roles: 打点形成

### state_chain
resource_loop(existing) -> こたつむり (attack_permission:-2 / board:+1 / damage_pressure:+3 / defense:+1 / loop_output_to_win:+1 / opponent_action_lock:+1 / repeated_attack:+1) -> ベイB パオパオ (board:+1 / damage_pressure:+3 / graveyard:+1 / hand:+1 / loop_output_to_win:+1 / mana:+1 / opponent_deck_pressure:+1 / repeated_attack:+1 / resource_loop:+2 / tempo:+1) -> direct_attack_win (attack_permission:-2 / board:+2 / damage_pressure:+6 / defense:+1 / graveyard:+1 / hand:+1 / loop_output_to_win:+2 / mana:+1 / opponent_action_lock:+1 / opponent_deck_pressure:+1 / repeated_attack:+2 / resource_loop:+2 / tempo:+1)

### produced_states
{"attack_permission": -2, "board": 2, "damage_pressure": 6, "defense": 1, "graveyard": 1, "hand": 1, "loop_output_to_win": 2, "mana": 1, "opponent_action_lock": 1, "opponent_deck_pressure": 1, "repeated_attack": 2, "resource_loop": 2, "tempo": 1}

### proof_comment
direct_attack_winへの状態変換候補です。seed=こたつむり / ベイB パオパオ。作れている状態は attack_permission:-2 / board:+2 / damage_pressure:+6 / defense:+1 / graveyard:+1 / hand:+1 / loop_output_to_win:+2 / mana:+1 / opponent_action_lock:+1 / opponent_deck_pressure:+1 / repeated_attack:+2 / resource_loop:+2 / tempo:+1。不足は attack_permission。次は 打点形成 を探します。

## 9. proof_based damage_overflow_win #1

- candidate_origin: proof_based
- route_type: damage_overflow_win
- proof_score: 100
- route_seed_cards: 運命の選択
- total_cost: 4
- missing_states: なし
- required_support_roles: なし

### state_chain
運命の選択 (action_window:+1 / board:+1 / damage_pressure:+5 / loop_output_to_win:+1 / repeated_attack:+1 / resource_loop:+2 / summon_permission:+1 / tempo:+3) -> damage_overflow_win (action_window:+1 / board:+1 / damage_pressure:+5 / loop_output_to_win:+1 / repeated_attack:+1 / resource_loop:+2 / summon_permission:+1 / tempo:+3)

### produced_states
{"action_window": 1, "board": 1, "damage_pressure": 5, "loop_output_to_win": 1, "repeated_attack": 1, "resource_loop": 2, "summon_permission": 1, "tempo": 3}

### proof_comment
damage_overflow_winの必須状態を満たす勝利証明候補です。seed=運命の選択。作れている状態は action_window:+1 / board:+1 / damage_pressure:+5 / loop_output_to_win:+1 / repeated_attack:+1 / resource_loop:+2 / summon_permission:+1 / tempo:+3。

## 10. proof_based damage_overflow_win #2

- candidate_origin: proof_based
- route_type: damage_overflow_win
- proof_score: 100
- route_seed_cards: ベイB パオパオ
- total_cost: 1
- missing_states: なし
- required_support_roles: なし

### state_chain
ベイB パオパオ (board:+1 / damage_pressure:+3 / graveyard:+1 / hand:+1 / loop_output_to_win:+1 / mana:+1 / opponent_deck_pressure:+1 / repeated_attack:+1 / resource_loop:+2 / tempo:+1) -> damage_overflow_win (board:+1 / damage_pressure:+3 / graveyard:+1 / hand:+1 / loop_output_to_win:+1 / mana:+1 / opponent_deck_pressure:+1 / repeated_attack:+1 / resource_loop:+2 / tempo:+1)

### produced_states
{"board": 1, "damage_pressure": 3, "graveyard": 1, "hand": 1, "loop_output_to_win": 1, "mana": 1, "opponent_deck_pressure": 1, "repeated_attack": 1, "resource_loop": 2, "tempo": 1}

### proof_comment
damage_overflow_winの必須状態を満たす勝利証明候補です。seed=ベイB パオパオ。作れている状態は board:+1 / damage_pressure:+3 / graveyard:+1 / hand:+1 / loop_output_to_win:+1 / mana:+1 / opponent_deck_pressure:+1 / repeated_attack:+1 / resource_loop:+2 / tempo:+1。
