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
| proof_based direct_attack_win #1 | direct_attack_win | 72 | 2 | 2 | 天斬の悪魔龍 ジュランデス / ベイB パオパオ | attack_permission | 打点形成 |
| proof_based direct_attack_win #2 | direct_attack_win | 72 | 2 | 2 | 天斬の悪魔龍 ジュランデス / D2B バブール | attack_permission | 打点形成 |
| proof_based direct_attack_win #3 | direct_attack_win | 72 | 2 | 2 | 天斬の悪魔龍 ジュランデス / 連鎖庇護類 ジュラピ | attack_permission | 打点形成 |
| proof_based direct_attack_win #4 | direct_attack_win | 72 | 2 | 2 | 天斬の悪魔龍 ジュランデス / 駱駝の御輿 | attack_permission | 打点形成 |
| proof_based direct_attack_win #5 | direct_attack_win | 72 | 2 | 2 | ベイB パオパオ / 天斬の悪魔龍 ジュランデス | attack_permission | 打点形成 |
| proof_based direct_attack_win #6 | direct_attack_win | 72 | 2 | 2 | D2B バブール / 天斬の悪魔龍 ジュランデス | attack_permission | 打点形成 |
| proof_based direct_attack_win #7 | direct_attack_win | 71 | 1 | 1 | 天斬の悪魔龍 ジュランデス | attack_permission | 打点形成 |
| proof_based direct_attack_win #8 | direct_attack_win | 71 | 3 | 2 | 天斬の悪魔龍 ジュランデス / こたつむり | attack_permission | 打点形成 |
| proof_based damage_overflow_win #1 | damage_overflow_win | 100 | 1 | 1 | 天斬の悪魔龍 ジュランデス |  |  |
| proof_based damage_overflow_win #2 | damage_overflow_win | 100 | 4 | 1 | 相撲 Dr.ウンリュウ |  |  |
| proof_based damage_overflow_win #3 | damage_overflow_win | 100 | 3 | 1 | ピュア・ランガ |  |  |
| proof_based damage_overflow_win #4 | damage_overflow_win | 100 | 2 | 1 | 蛙跳び フロッグ |  |  |
| proof_based damage_overflow_win #5 | damage_overflow_win | 100 | 5 | 1 | ジャッジメント・タイム |  |  |
| proof_based damage_overflow_win #6 | damage_overflow_win | 100 | 6 | 1 | 連珠の精霊アガピトス |  |  |
| proof_based damage_overflow_win #7 | damage_overflow_win | 100 | 5 | 1 | 侵略者 ノイバウテン |  |  |
| proof_based damage_overflow_win #8 | damage_overflow_win | 100 | 1 | 1 | ベイB パオパオ |  |  |
| proof_based alternate_effect_win #1 | alternate_effect_win | 86 | 4 | 2 | 完全防御革命 / ベイB パオパオ |  |  |
| proof_based alternate_effect_win #2 | alternate_effect_win | 86 | 4 | 2 | 完全防御革命 / D2B バブール |  |  |
| proof_based alternate_effect_win #3 | alternate_effect_win | 86 | 4 | 2 | 完全防御革命 / ベイB ポレポレ |  |  |
| proof_based alternate_effect_win #4 | alternate_effect_win | 86 | 4 | 2 | 完全防御革命 / ベイB ソーター |  |  |
| proof_based alternate_effect_win #5 | alternate_effect_win | 86 | 4 | 2 | 完全防御革命 / ベイB クッジャ |  |  |
| proof_based alternate_effect_win #6 | alternate_effect_win | 86 | 4 | 2 | 剛勇王機フルメタル・レモン / ベイB パオパオ |  |  |
| proof_based alternate_effect_win #7 | alternate_effect_win | 86 | 4 | 2 | 剛勇王機フルメタル・レモン / D2B バブール |  |  |
| proof_based alternate_effect_win #8 | alternate_effect_win | 86 | 4 | 2 | 剛勇王機フルメタル・レモン / ベイB ポレポレ |  |  |
| proof_based opponent_deckout_win #1 | opponent_deckout_win | 89 | 3 | 1 | 竜のフレア・エッグ |  |  |
| proof_based opponent_deckout_win #2 | opponent_deckout_win | 88 | 4 | 1 | 戦攻妖精クルメル |  |  |
| proof_based opponent_deckout_win #3 | opponent_deckout_win | 88 | 2 | 2 | D2B バブール / 葬送の守護者ドルルン |  |  |
| proof_based opponent_deckout_win #4 | opponent_deckout_win | 88 | 2 | 2 | 葬送の守護者ドルルン / D2B バブール |  |  |
| proof_based opponent_deckout_win #5 | opponent_deckout_win | 88 | 2 | 2 | 葬送の守護者ドルルン / ベイB パオパオ |  |  |
| proof_based opponent_deckout_win #6 | opponent_deckout_win | 88 | 2 | 2 | 葬送の守護者ドルルン / 天斬の悪魔龍 ジュランデス |  |  |

## 上位候補詳細

## 1. proof_based direct_attack_win #1

- candidate_origin: proof_based
- route_type: direct_attack_win
- proof_score: 72
- route_seed_cards: 天斬の悪魔龍 ジュランデス / ベイB パオパオ
- total_cost: 2
- missing_states: attack_permission
- required_support_roles: 打点形成

### state_chain
resource_loop(existing) -> 天斬の悪魔龍 ジュランデス (action_window:+2 / board:+1 / damage_pressure:+5 / disruption:+3 / loop_output_to_win:+1 / repeated_attack:+1 / resource_loop:+2 / tempo:+4 / turn_count:+1 / win_progress:+2 / zone_change_permission:+1) -> ベイB パオパオ (board:+1 / damage_pressure:+5 / graveyard:+1 / hand:+1 / loop_output_to_win:+1 / mana:+1 / opponent_deck_pressure:+2 / repeated_attack:+1 / resource_loop:+3 / tempo:+2) -> direct_attack_win (action_window:+2 / board:+2 / damage_pressure:+10 / disruption:+3 / graveyard:+1 / hand:+1 / loop_output_to_win:+2 / mana:+1 / opponent_deck_pressure:+2 / repeated_attack:+2 / resource_loop:+5 / tempo:+6 / turn_count:+1 / win_progress:+2 / zone_change_permission:+1)

### produced_states
{"action_window": 2, "board": 2, "damage_pressure": 10, "disruption": 3, "graveyard": 1, "hand": 1, "loop_output_to_win": 2, "mana": 1, "opponent_deck_pressure": 2, "repeated_attack": 2, "resource_loop": 5, "tempo": 6, "turn_count": 1, "win_progress": 2, "zone_change_permission": 1}

### proof_comment
direct_attack_winへの状態変換候補です。seed=天斬の悪魔龍 ジュランデス / ベイB パオパオ。作れている状態は action_window:+2 / board:+2 / damage_pressure:+10 / disruption:+3 / graveyard:+1 / hand:+1 / loop_output_to_win:+2 / mana:+1 / opponent_deck_pressure:+2 / repeated_attack:+2 / resource_loop:+5 / tempo:+6 / turn_count:+1 / win_progress:+2 / zone_change_permission:+1。不足は attack_permission。次は 打点形成 を探します。

## 2. proof_based direct_attack_win #2

- candidate_origin: proof_based
- route_type: direct_attack_win
- proof_score: 72
- route_seed_cards: 天斬の悪魔龍 ジュランデス / D2B バブール
- total_cost: 2
- missing_states: attack_permission
- required_support_roles: 打点形成

### state_chain
resource_loop(existing) -> 天斬の悪魔龍 ジュランデス (action_window:+2 / board:+1 / damage_pressure:+5 / disruption:+3 / loop_output_to_win:+1 / repeated_attack:+1 / resource_loop:+2 / tempo:+4 / turn_count:+1 / win_progress:+2 / zone_change_permission:+1) -> D2B バブール (board:+1 / damage_pressure:+5 / defense:+1 / disruption:+2 / graveyard:+1 / hand:+1 / loop_output_to_win:+1 / opponent_deck_pressure:+2 / repeated_attack:+1 / resource_loop:+1 / tempo:+1) -> direct_attack_win (action_window:+2 / board:+2 / damage_pressure:+10 / defense:+1 / disruption:+5 / graveyard:+1 / hand:+1 / loop_output_to_win:+2 / opponent_deck_pressure:+2 / repeated_attack:+2 / resource_loop:+3 / tempo:+5 / turn_count:+1 / win_progress:+2 / zone_change_permission:+1)

### produced_states
{"action_window": 2, "board": 2, "damage_pressure": 10, "defense": 1, "disruption": 5, "graveyard": 1, "hand": 1, "loop_output_to_win": 2, "opponent_deck_pressure": 2, "repeated_attack": 2, "resource_loop": 3, "tempo": 5, "turn_count": 1, "win_progress": 2, "zone_change_permission": 1}

### proof_comment
direct_attack_winへの状態変換候補です。seed=天斬の悪魔龍 ジュランデス / D2B バブール。作れている状態は action_window:+2 / board:+2 / damage_pressure:+10 / defense:+1 / disruption:+5 / graveyard:+1 / hand:+1 / loop_output_to_win:+2 / opponent_deck_pressure:+2 / repeated_attack:+2 / resource_loop:+3 / tempo:+5 / turn_count:+1 / win_progress:+2 / zone_change_permission:+1。不足は attack_permission。次は 打点形成 を探します。

## 3. proof_based direct_attack_win #3

- candidate_origin: proof_based
- route_type: direct_attack_win
- proof_score: 72
- route_seed_cards: 天斬の悪魔龍 ジュランデス / 連鎖庇護類 ジュラピ
- total_cost: 2
- missing_states: attack_permission
- required_support_roles: 打点形成

### state_chain
天斬の悪魔龍 ジュランデス (action_window:+2 / board:+1 / damage_pressure:+5 / disruption:+3 / loop_output_to_win:+1 / repeated_attack:+1 / resource_loop:+2 / tempo:+4 / turn_count:+1 / win_progress:+2 / zone_change_permission:+1) -> 連鎖庇護類 ジュラピ (action_window:+1 / board:+1 / damage_pressure:+1 / loop_output_to_win:+1 / opponent_action_lock:+2 / summon_permission:-1 / tempo:+2 / win_progress:+1) -> direct_attack_win (action_window:+3 / board:+2 / damage_pressure:+6 / disruption:+3 / loop_output_to_win:+2 / opponent_action_lock:+2 / repeated_attack:+1 / resource_loop:+2 / summon_permission:-1 / tempo:+6 / turn_count:+1 / win_progress:+3 / zone_change_permission:+1)

### produced_states
{"action_window": 3, "board": 2, "damage_pressure": 6, "disruption": 3, "loop_output_to_win": 2, "opponent_action_lock": 2, "repeated_attack": 1, "resource_loop": 2, "summon_permission": -1, "tempo": 6, "turn_count": 1, "win_progress": 3, "zone_change_permission": 1}

### proof_comment
direct_attack_winへの状態変換候補です。seed=天斬の悪魔龍 ジュランデス / 連鎖庇護類 ジュラピ。作れている状態は action_window:+3 / board:+2 / damage_pressure:+6 / disruption:+3 / loop_output_to_win:+2 / opponent_action_lock:+2 / repeated_attack:+1 / resource_loop:+2 / summon_permission:-1 / tempo:+6 / turn_count:+1 / win_progress:+3 / zone_change_permission:+1。不足は attack_permission。次は 打点形成 を探します。

## 4. proof_based direct_attack_win #4

- candidate_origin: proof_based
- route_type: direct_attack_win
- proof_score: 72
- route_seed_cards: 天斬の悪魔龍 ジュランデス / 駱駝の御輿
- total_cost: 2
- missing_states: attack_permission
- required_support_roles: 打点形成

### state_chain
天斬の悪魔龍 ジュランデス (action_window:+2 / board:+1 / damage_pressure:+5 / disruption:+3 / loop_output_to_win:+1 / repeated_attack:+1 / resource_loop:+2 / tempo:+4 / turn_count:+1 / win_progress:+2 / zone_change_permission:+1) -> 駱駝の御輿 (action_window:+1 / attack_permission:-2 / board:+1 / damage_pressure:+1 / defense:+1 / loop_output_to_win:+1 / opponent_action_lock:+1 / summon_permission:+1 / tempo:+2 / win_progress:+1) -> direct_attack_win (action_window:+3 / attack_permission:-2 / board:+2 / damage_pressure:+6 / defense:+1 / disruption:+3 / loop_output_to_win:+2 / opponent_action_lock:+1 / repeated_attack:+1 / resource_loop:+2 / summon_permission:+1 / tempo:+6 / turn_count:+1 / win_progress:+3 / zone_change_permission:+1)

### produced_states
{"action_window": 3, "attack_permission": -2, "board": 2, "damage_pressure": 6, "defense": 1, "disruption": 3, "loop_output_to_win": 2, "opponent_action_lock": 1, "repeated_attack": 1, "resource_loop": 2, "summon_permission": 1, "tempo": 6, "turn_count": 1, "win_progress": 3, "zone_change_permission": 1}

### proof_comment
direct_attack_winへの状態変換候補です。seed=天斬の悪魔龍 ジュランデス / 駱駝の御輿。作れている状態は action_window:+3 / attack_permission:-2 / board:+2 / damage_pressure:+6 / defense:+1 / disruption:+3 / loop_output_to_win:+2 / opponent_action_lock:+1 / repeated_attack:+1 / resource_loop:+2 / summon_permission:+1 / tempo:+6 / turn_count:+1 / win_progress:+3 / zone_change_permission:+1。不足は attack_permission。次は 打点形成 を探します。

## 5. proof_based direct_attack_win #5

- candidate_origin: proof_based
- route_type: direct_attack_win
- proof_score: 72
- route_seed_cards: ベイB パオパオ / 天斬の悪魔龍 ジュランデス
- total_cost: 2
- missing_states: attack_permission
- required_support_roles: 打点形成

### state_chain
resource_loop(existing) -> ベイB パオパオ (board:+1 / damage_pressure:+5 / graveyard:+1 / hand:+1 / loop_output_to_win:+1 / mana:+1 / opponent_deck_pressure:+2 / repeated_attack:+1 / resource_loop:+3 / tempo:+2) -> 天斬の悪魔龍 ジュランデス (action_window:+2 / board:+1 / damage_pressure:+5 / disruption:+3 / loop_output_to_win:+1 / repeated_attack:+1 / resource_loop:+2 / tempo:+4 / turn_count:+1 / win_progress:+2 / zone_change_permission:+1) -> direct_attack_win (action_window:+2 / board:+2 / damage_pressure:+10 / disruption:+3 / graveyard:+1 / hand:+1 / loop_output_to_win:+2 / mana:+1 / opponent_deck_pressure:+2 / repeated_attack:+2 / resource_loop:+5 / tempo:+6 / turn_count:+1 / win_progress:+2 / zone_change_permission:+1)

### produced_states
{"action_window": 2, "board": 2, "damage_pressure": 10, "disruption": 3, "graveyard": 1, "hand": 1, "loop_output_to_win": 2, "mana": 1, "opponent_deck_pressure": 2, "repeated_attack": 2, "resource_loop": 5, "tempo": 6, "turn_count": 1, "win_progress": 2, "zone_change_permission": 1}

### proof_comment
direct_attack_winへの状態変換候補です。seed=ベイB パオパオ / 天斬の悪魔龍 ジュランデス。作れている状態は action_window:+2 / board:+2 / damage_pressure:+10 / disruption:+3 / graveyard:+1 / hand:+1 / loop_output_to_win:+2 / mana:+1 / opponent_deck_pressure:+2 / repeated_attack:+2 / resource_loop:+5 / tempo:+6 / turn_count:+1 / win_progress:+2 / zone_change_permission:+1。不足は attack_permission。次は 打点形成 を探します。

## 6. proof_based direct_attack_win #6

- candidate_origin: proof_based
- route_type: direct_attack_win
- proof_score: 72
- route_seed_cards: D2B バブール / 天斬の悪魔龍 ジュランデス
- total_cost: 2
- missing_states: attack_permission
- required_support_roles: 打点形成

### state_chain
resource_loop(existing) -> D2B バブール (board:+1 / damage_pressure:+5 / defense:+1 / disruption:+2 / graveyard:+1 / hand:+1 / loop_output_to_win:+1 / opponent_deck_pressure:+2 / repeated_attack:+1 / resource_loop:+1 / tempo:+1) -> 天斬の悪魔龍 ジュランデス (action_window:+2 / board:+1 / damage_pressure:+5 / disruption:+3 / loop_output_to_win:+1 / repeated_attack:+1 / resource_loop:+2 / tempo:+4 / turn_count:+1 / win_progress:+2 / zone_change_permission:+1) -> direct_attack_win (action_window:+2 / board:+2 / damage_pressure:+10 / defense:+1 / disruption:+5 / graveyard:+1 / hand:+1 / loop_output_to_win:+2 / opponent_deck_pressure:+2 / repeated_attack:+2 / resource_loop:+3 / tempo:+5 / turn_count:+1 / win_progress:+2 / zone_change_permission:+1)

### produced_states
{"action_window": 2, "board": 2, "damage_pressure": 10, "defense": 1, "disruption": 5, "graveyard": 1, "hand": 1, "loop_output_to_win": 2, "opponent_deck_pressure": 2, "repeated_attack": 2, "resource_loop": 3, "tempo": 5, "turn_count": 1, "win_progress": 2, "zone_change_permission": 1}

### proof_comment
direct_attack_winへの状態変換候補です。seed=D2B バブール / 天斬の悪魔龍 ジュランデス。作れている状態は action_window:+2 / board:+2 / damage_pressure:+10 / defense:+1 / disruption:+5 / graveyard:+1 / hand:+1 / loop_output_to_win:+2 / opponent_deck_pressure:+2 / repeated_attack:+2 / resource_loop:+3 / tempo:+5 / turn_count:+1 / win_progress:+2 / zone_change_permission:+1。不足は attack_permission。次は 打点形成 を探します。

## 7. proof_based direct_attack_win #7

- candidate_origin: proof_based
- route_type: direct_attack_win
- proof_score: 71
- route_seed_cards: 天斬の悪魔龍 ジュランデス
- total_cost: 1
- missing_states: attack_permission
- required_support_roles: 打点形成

### state_chain
天斬の悪魔龍 ジュランデス (action_window:+2 / board:+1 / damage_pressure:+5 / disruption:+3 / loop_output_to_win:+1 / repeated_attack:+1 / resource_loop:+2 / tempo:+4 / turn_count:+1 / win_progress:+2 / zone_change_permission:+1) -> direct_attack_win (action_window:+2 / board:+1 / damage_pressure:+5 / disruption:+3 / loop_output_to_win:+1 / repeated_attack:+1 / resource_loop:+2 / tempo:+4 / turn_count:+1 / win_progress:+2 / zone_change_permission:+1)

### produced_states
{"action_window": 2, "board": 1, "damage_pressure": 5, "disruption": 3, "loop_output_to_win": 1, "repeated_attack": 1, "resource_loop": 2, "tempo": 4, "turn_count": 1, "win_progress": 2, "zone_change_permission": 1}

### proof_comment
direct_attack_winへの状態変換候補です。seed=天斬の悪魔龍 ジュランデス。作れている状態は action_window:+2 / board:+1 / damage_pressure:+5 / disruption:+3 / loop_output_to_win:+1 / repeated_attack:+1 / resource_loop:+2 / tempo:+4 / turn_count:+1 / win_progress:+2 / zone_change_permission:+1。不足は attack_permission。次は 打点形成 を探します。

## 8. proof_based direct_attack_win #8

- candidate_origin: proof_based
- route_type: direct_attack_win
- proof_score: 71
- route_seed_cards: 天斬の悪魔龍 ジュランデス / こたつむり
- total_cost: 3
- missing_states: attack_permission
- required_support_roles: 打点形成

### state_chain
天斬の悪魔龍 ジュランデス (action_window:+2 / board:+1 / damage_pressure:+5 / disruption:+3 / loop_output_to_win:+1 / repeated_attack:+1 / resource_loop:+2 / tempo:+4 / turn_count:+1 / win_progress:+2 / zone_change_permission:+1) -> こたつむり (attack_permission:-2 / board:+1 / damage_pressure:+5 / defense:+1 / loop_output_to_win:+1 / opponent_action_lock:+1 / repeated_attack:+1 / tempo:+1) -> direct_attack_win (action_window:+2 / attack_permission:-2 / board:+2 / damage_pressure:+10 / defense:+1 / disruption:+3 / loop_output_to_win:+2 / opponent_action_lock:+1 / repeated_attack:+2 / resource_loop:+2 / tempo:+5 / turn_count:+1 / win_progress:+2 / zone_change_permission:+1)

### produced_states
{"action_window": 2, "attack_permission": -2, "board": 2, "damage_pressure": 10, "defense": 1, "disruption": 3, "loop_output_to_win": 2, "opponent_action_lock": 1, "repeated_attack": 2, "resource_loop": 2, "tempo": 5, "turn_count": 1, "win_progress": 2, "zone_change_permission": 1}

### proof_comment
direct_attack_winへの状態変換候補です。seed=天斬の悪魔龍 ジュランデス / こたつむり。作れている状態は action_window:+2 / attack_permission:-2 / board:+2 / damage_pressure:+10 / defense:+1 / disruption:+3 / loop_output_to_win:+2 / opponent_action_lock:+1 / repeated_attack:+2 / resource_loop:+2 / tempo:+5 / turn_count:+1 / win_progress:+2 / zone_change_permission:+1。不足は attack_permission。次は 打点形成 を探します。

## 9. proof_based damage_overflow_win #1

- candidate_origin: proof_based
- route_type: damage_overflow_win
- proof_score: 100
- route_seed_cards: 天斬の悪魔龍 ジュランデス
- total_cost: 1
- missing_states: なし
- required_support_roles: なし

### state_chain
天斬の悪魔龍 ジュランデス (action_window:+2 / board:+1 / damage_pressure:+5 / disruption:+3 / loop_output_to_win:+1 / repeated_attack:+1 / resource_loop:+2 / tempo:+4 / turn_count:+1 / win_progress:+2 / zone_change_permission:+1) -> damage_overflow_win (action_window:+2 / board:+1 / damage_pressure:+5 / disruption:+3 / loop_output_to_win:+1 / repeated_attack:+1 / resource_loop:+2 / tempo:+4 / turn_count:+1 / win_progress:+2 / zone_change_permission:+1)

### produced_states
{"action_window": 2, "board": 1, "damage_pressure": 5, "disruption": 3, "loop_output_to_win": 1, "repeated_attack": 1, "resource_loop": 2, "tempo": 4, "turn_count": 1, "win_progress": 2, "zone_change_permission": 1}

### proof_comment
damage_overflow_winの必須状態を満たす勝利証明候補です。seed=天斬の悪魔龍 ジュランデス。作れている状態は action_window:+2 / board:+1 / damage_pressure:+5 / disruption:+3 / loop_output_to_win:+1 / repeated_attack:+1 / resource_loop:+2 / tempo:+4 / turn_count:+1 / win_progress:+2 / zone_change_permission:+1。

## 10. proof_based damage_overflow_win #2

- candidate_origin: proof_based
- route_type: damage_overflow_win
- proof_score: 100
- route_seed_cards: 相撲 Dr.ウンリュウ
- total_cost: 4
- missing_states: なし
- required_support_roles: なし

### state_chain
相撲 Dr.ウンリュウ (action_window:+1 / board:+1 / damage_pressure:+5 / graveyard:+1 / loop_output_to_win:+1 / opponent_deck_pressure:+2 / repeated_attack:+1 / resource_loop:+1 / summon_permission:+1 / tempo:+3 / win_progress:+1) -> damage_overflow_win (action_window:+1 / board:+1 / damage_pressure:+5 / graveyard:+1 / loop_output_to_win:+1 / opponent_deck_pressure:+2 / repeated_attack:+1 / resource_loop:+1 / summon_permission:+1 / tempo:+3 / win_progress:+1)

### produced_states
{"action_window": 1, "board": 1, "damage_pressure": 5, "graveyard": 1, "loop_output_to_win": 1, "opponent_deck_pressure": 2, "repeated_attack": 1, "resource_loop": 1, "summon_permission": 1, "tempo": 3, "win_progress": 1}

### proof_comment
damage_overflow_winの必須状態を満たす勝利証明候補です。seed=相撲 Dr.ウンリュウ。作れている状態は action_window:+1 / board:+1 / damage_pressure:+5 / graveyard:+1 / loop_output_to_win:+1 / opponent_deck_pressure:+2 / repeated_attack:+1 / resource_loop:+1 / summon_permission:+1 / tempo:+3 / win_progress:+1。
