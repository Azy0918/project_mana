from __future__ import annotations

from typing import Any


def generate_feedback(deck_name: str, stats: dict[str, Any]) -> list[str]:
    comments = []

    overall = stats.get("overall", {})
    win_rate = overall.get("win_rate", 0)
    matches = overall.get("matches", 0)
    evaluation = stats.get("evaluation")
    score_gap = stats.get("score_gap")
    meta_gap = stats.get("meta_gap")

    if matches < 5:
        comments.append("試合数が少ないため、まずは追加ログを集めると判断精度が上がります。")
    elif win_rate >= 60:
        comments.append("実戦勝率は良好です。現構築を基準に、苦手対面だけを重点的に調整する価値があります。")
    elif win_rate >= 45:
        comments.append("実戦勝率は中程度です。活躍カードと腐ったカードを比較して、数枚単位の調整が有効です。")
    else:
        comments.append("実戦勝率が低めです。初動、受け札、フィニッシャーの配分を見直す価値があります。")

    if evaluation and score_gap is not None:
        if score_gap <= -20:
            comments.append("AI評価スコアに対して実勝率が低めです。想定より実戦で機能していないカードや対面を確認してください。")
        elif score_gap >= 15:
            comments.append("AI評価スコアより実勝率が高めです。タグ評価では拾えていない強みがある可能性があります。")

    if evaluation and meta_gap is not None and meta_gap <= -20:
        comments.append("メタ適性スコアに対して実勝率が低めです。仮想メタ評価と実環境のズレを確認してください。")

    by_opponent = stats.get("by_opponent", {})
    weak_opponents = [
        name
        for name, item in by_opponent.items()
        if item.get("matches", 0) >= 2 and item.get("win_rate", 0) < 45
    ]
    if weak_opponents:
        comments.append(
            "苦手対面として "
            + "、".join(weak_opponents)
            + " が見えています。対策カードやプレイ方針を個別に検討してください。"
        )

    by_play_order = stats.get("by_play_order", {})
    first = by_play_order.get("先攻", {}).get("win_rate")
    second = by_play_order.get("後攻", {}).get("win_rate")
    if first is not None and second is not None and first - second >= 20:
        comments.append("後攻時の勝率が低めです。軽量受け札や2コスト初動の増量が候補になります。")
    elif second is not None and first is not None and second - first >= 20:
        comments.append("後攻時の勝率が高めです。受け性能は十分な可能性があります。先攻時の押し切り性能を確認してください。")

    dead_cards = stats.get("dead_cards", [])
    if dead_cards:
        top_dead = dead_cards[0][0]
        comments.append(f"腐ったカードとして `{top_dead}` の記録が多いです。枚数調整や役割の再確認が候補です。")

    key_cards = stats.get("key_cards", [])
    if key_cards:
        top_key = key_cards[0][0]
        comments.append(f"活躍カードとして `{top_key}` の記録が多いです。デッキの主軸として維持する価値があります。")

    if not comments:
        comments.append(f"`{deck_name}` は追加ログを集めながら、対面別の傾向を確認してください。")

    return comments
