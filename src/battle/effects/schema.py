from __future__ import annotations

from typing import Any

# EffectScript: 能力テキストをルールカーネルが実行できる形にした中間表現。
#
# {
#   "card_id": "DMPC-0001",
#   "abilities": [
#     {"trigger": "on_cast", "actions": [{"op": "deck_top_to_mana", "count": 1}]}
#   ]
# }

KNOWN_TRIGGERS = {
    "on_cast",       # 呪文を唱えた時
    "on_play",       # クリーチャーが出た時
    "s_trigger",     # S・トリガー(シールドから手札に加わった時)
    "on_attack",     # 攻撃する時
    "on_destroyed",  # 破壊された時
}

# 命令セット第1弾(ロードマップv1.2)。op名 -> 許可パラメータ(必須は count のみ)
KNOWN_OPS: dict[str, set[str]] = {
    "draw": {"count"},
    "deck_top_to_mana": {"count"},
    "destroy_creature": {"count", "scope", "max_power"},
    "bounce_creature": {"count", "scope"},
    "tap_creature": {"count", "scope"},
}

KNOWN_SCOPES = {"opponent", "self"}


def validate_effect_script(script: dict[str, Any]) -> list[str]:
    """EffectScriptを検証し、エラーメッセージの一覧を返す。空なら妥当。"""
    errors: list[str] = []
    if not isinstance(script, dict):
        return ["EffectScriptはdictで指定してください"]
    if not script.get("card_id"):
        errors.append("card_idが未設定です")
    abilities = script.get("abilities")
    if not isinstance(abilities, list):
        return errors + ["abilitiesはリストで指定してください"]
    for ability_index, ability in enumerate(abilities):
        prefix = f"abilities[{ability_index}]"
        if not isinstance(ability, dict):
            errors.append(f"{prefix}: dictで指定してください")
            continue
        trigger = ability.get("trigger")
        if trigger not in KNOWN_TRIGGERS:
            errors.append(f"{prefix}: 未知のtrigger '{trigger}' (対応: {sorted(KNOWN_TRIGGERS)})")
        actions = ability.get("actions")
        if not isinstance(actions, list) or not actions:
            errors.append(f"{prefix}: actionsは1件以上のリストで指定してください")
            continue
        for action_index, action in enumerate(actions):
            errors.extend(_validate_action(action, f"{prefix}.actions[{action_index}]"))
    return errors


def _validate_action(action: Any, prefix: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(action, dict):
        return [f"{prefix}: dictで指定してください"]
    op = action.get("op")
    if op not in KNOWN_OPS:
        return [f"{prefix}: 未知のop '{op}' (対応: {sorted(KNOWN_OPS)})"]
    allowed = KNOWN_OPS[op] | {"op"}
    for key in action:
        if key not in allowed:
            errors.append(f"{prefix}: op '{op}' に不要なパラメータ '{key}'")
    count = action.get("count", 1)
    if not isinstance(count, int) or count < 1:
        errors.append(f"{prefix}: countは1以上の整数で指定してください")
    scope = action.get("scope")
    if scope is not None and scope not in KNOWN_SCOPES:
        errors.append(f"{prefix}: 未知のscope '{scope}' (対応: {sorted(KNOWN_SCOPES)})")
    max_power = action.get("max_power")
    if max_power is not None and (not isinstance(max_power, int) or max_power < 0):
        errors.append(f"{prefix}: max_powerは0以上の整数で指定してください")
    return errors
