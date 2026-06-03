from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.effect_semantics import infer_effect_semantics


@dataclass(frozen=True)
class RuleSource:
    title: str
    url: str
    source_type: str
    checked_at: str
    note: str


@dataclass(frozen=True)
class RuleConcept:
    key: str
    name: str
    summary: str
    state_axes: list[str]
    detection_signals: list[str]
    why_it_matters: str
    mana_model_hint: str


RULE_SOURCES = [
    RuleSource(
        title="デュエル・マスターズ総合ゲームルール",
        url="https://dm.takaratomy.co.jp/rule/rulechange/",
        source_type="公式総合ルール",
        checked_at="2026-05-30",
        note="公式ページでは総合ゲームルール Ver.1.50 が2026-04-10最終更新として掲載されています。",
    ),
    RuleSource(
        title="デュエル・マスターズ 公式Q&A",
        url="https://dm.takaratomy.co.jp/rule/qa/",
        source_type="公式裁定",
        checked_at="2026-05-30",
        note="個別カードや能力の裁定確認に使う一次情報候補です。",
    ),
    RuleSource(
        title="読んでルールをおぼえよう",
        url="https://dm.takaratomy.co.jp/rule/basic/basic08/",
        source_type="公式基本ルール",
        checked_at="2026-05-30",
        note="基本的なゲーム進行、デッキ、シールド、マナ、攻撃の理解に使います。",
    ),
]


RULE_CONCEPTS = [
    RuleConcept(
        key="turn_structure",
        name="ターン構造",
        summary="ドロー、マナチャージ、メイン行動、攻撃など、行動できる窓を分けて扱う。",
        state_axes=["action_window", "turn_count", "tempo"],
        detection_signals=["ターンを追加", "もう一度", "このターン", "次のターン"],
        why_it_matters="同じカードでも、使えるタイミングが早いほどデッキ全体の到達ターンが変わります。",
        mana_model_hint="行動回数や追加ターンは単なるドローより重い tempo / action_window の変化として扱う。",
    ),
    RuleConcept(
        key="zone_system",
        name="ゾーン移動",
        summary="手札、山札、マナ、墓地、バトルゾーン、シールドなどの移動を状態変化として読む。",
        state_axes=["hand", "mana", "graveyard", "board", "shield", "zone_change_permission"],
        detection_signals=["手札に加える", "マナゾーンに置く", "墓地に置く", "バトルゾーンに出す", "シールド化"],
        why_it_matters="コンボは多くの場合、あるゾーンの資源を別ゾーンの勝ち筋へ変換します。",
        mana_model_hint="from_zone -> to_zone を保存し、別カードの要求ゾーンと接続する。",
    ),
    RuleConcept(
        key="cost_and_permission",
        name="コストと許可",
        summary="召喚、詠唱、コスト支払い、コスト踏み倒し、G・ゼロなどを制約解除として扱う。",
        state_axes=["summon_permission", "cast_permission", "tempo", "action_window"],
        detection_signals=["コストを支払わず", "G・ゼロ", "召喚してもよい", "唱えてもよい", "コストを少なく"],
        why_it_matters="強いデッキはコスト制約を外して、通常より早いターンに高価値行動へ到達します。",
        mana_model_hint="cost_bypass は手札枚数よりも tempo と permission の増加として評価する。",
    ),
    RuleConcept(
        key="trigger_and_replacement",
        name="誘発と置換",
        summary="出た時、攻撃する時、破壊される時、かわりになどを、状態変化の発火条件として扱う。",
        state_axes=["trigger_window", "replacement_destroy", "replacement_shield", "board_persistence"],
        detection_signals=["出た時", "攻撃する時", "破壊された時", "かわりに", "離れない", "破壊されない"],
        why_it_matters="盤面に残る、置換する、誘発を重ねるカードは見た目以上に状態を歪めます。",
        mana_model_hint="置換効果は防御値ではなく、通常の状態変化を書き換えるルール干渉として別軸化する。",
    ),
    RuleConcept(
        key="attack_and_shield",
        name="攻撃とシールド",
        summary="攻撃可能性、ブレイク、S・トリガー、シールド焼却を勝敗に近い状態として扱う。",
        state_axes=["attack_permission", "damage_pressure", "defense", "trigger_window", "replacement_shield"],
        detection_signals=["攻撃できない", "スピードアタッカー", "ブレイク", "S・トリガー", "シールドを墓地"],
        why_it_matters="シールドを経由する勝ち筋と、トリガーを消す勝ち筋はまったく別の強さを持ちます。",
        mana_model_hint="単なる打点ではなく、攻撃許可、トリガー発生、シールド置換を分けて評価する。",
    ),
    RuleConcept(
        key="evolution_stack",
        name="進化元・下敷き",
        summary="進化、退化、下に置く、一番上を離すなど、カード束の構造を扱う。",
        state_axes=["board", "resource_loop", "zone_change_permission", "win_progress"],
        detection_signals=["進化", "下に置く", "一番上", "進化クリーチャーの下", "退化"],
        why_it_matters="退化系はカード名タグより、束の構造変化として見ないと見落としやすいです。",
        mana_model_hint="evolution_stack を独立した中間状態として扱い、上面除去と下敷き利用を接続する。",
    ),
    RuleConcept(
        key="terminal_conditions",
        name="終端条件",
        summary="特殊勝利、追加ターン、山札切れ回避、敗北置換などをゲーム終端に近い変化として扱う。",
        state_axes=["alternate_win_progress", "turn_count", "lose_condition", "deck_out_prevention", "win_progress"],
        detection_signals=["ゲームに勝つ", "ターンを追加", "山札がなくなるかわり", "負けるかわり", "最後のカード"],
        why_it_matters="統計上の枚数評価では軽く見えても、終端条件はデッキの目的そのものになります。",
        mana_model_hint="terminal_effects は通常リソースとは別に、勝ち筋到達率と必要条件で評価する。",
    ),
    RuleConcept(
        key="lock_and_continuous",
        name="ロック・継続効果",
        summary="相手の召喚、詠唱、攻撃、能力、ゾーン移動を制限する継続的な干渉を扱う。",
        state_axes=["opponent_action_lock", "summon_permission", "cast_permission", "attack_permission", "effect_permission"],
        detection_signals=["できない", "唱えられない", "召喚できない", "攻撃できない", "能力を無視"],
        why_it_matters="相手の選択肢を消すカードは、自分のリソース増加と別の軸で勝率を上げます。",
        mana_model_hint="相手側 permission の減少として符号付き状態変化にする。",
    ),
]


def list_rule_sources() -> list[dict[str, str]]:
    return [source.__dict__.copy() for source in RULE_SOURCES]


def list_rule_concepts() -> list[dict[str, Any]]:
    return [
        {
            "key": concept.key,
            "name": concept.name,
            "summary": concept.summary,
            "state_axes": ";".join(concept.state_axes),
            "detection_signals": ";".join(concept.detection_signals),
            "why_it_matters": concept.why_it_matters,
            "mana_model_hint": concept.mana_model_hint,
        }
        for concept in RULE_CONCEPTS
    ]


def analyze_card_rule_hooks(card: dict[str, Any]) -> dict[str, Any]:
    semantics = infer_effect_semantics(card)
    text = str(card.get("text", "") or "")
    tags = str(card.get("tags", "") or "")
    haystack = f"{card.get('name', '')} {text} {tags} {' '.join(semantics.get('comments', []))}"

    matched: list[dict[str, Any]] = []
    for concept in RULE_CONCEPTS:
        signals = [signal for signal in concept.detection_signals if signal and signal in haystack]
        axes = [
            axis
            for axis in concept.state_axes
            if _axis_is_active(axis, semantics) or signals
        ]
        if signals or axes:
            matched.append(
                {
                    "ルール軸": concept.name,
                    "検出シグナル": ";".join(signals) if signals else "構造推定",
                    "状態軸": ";".join(axes),
                    "MANA解釈": concept.mana_model_hint,
                }
            )

    return {
        "card_name": card.get("name", ""),
        "matched_concepts": matched,
        "semantics": semantics,
        "next_questions": _build_next_questions(matched, semantics),
    }


def summarize_rule_understanding_status(feature_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    feature_summary = feature_summary or {}
    return {
        "status": "ルール構造理解 v1",
        "source_count": len(RULE_SOURCES),
        "concept_count": len(RULE_CONCEPTS),
        "feature_count": feature_summary.get("feature_count", 0),
        "focus": [
            "ゾーン移動を状態変換として読む",
            "コスト踏み倒しを制約解除として読む",
            "誘発・置換・ロックを通常リソースと別軸で読む",
            "特殊勝利と追加ターンを終端条件として読む",
        ],
        "limitations": [
            "公式総合ルール本文を完全な実行ルールとして解釈している段階ではありません。",
            "現時点ではカード本文キーワードとMANA用状態軸の対応付けです。",
            "裁定の正否を断定せず、検証すべきルール軸の候補を出します。",
        ],
    }


def _axis_is_active(axis: str, semantics: dict[str, Any]) -> bool:
    state_delta = semantics.get("state_delta", {})
    if state_delta.get(axis):
        return True
    if axis in {"summon_permission", "cast_permission", "zone_change_permission"}:
        return bool(semantics.get("constraint_breaks"))
    if axis in {"alternate_win_progress", "turn_count", "lose_condition", "deck_out_prevention"}:
        return bool(semantics.get("terminal_effects"))
    if axis in {"resource_loop", "replacement_destroy", "board_persistence"}:
        return bool(semantics.get("special_mechanics"))
    return False


def _build_next_questions(matched: list[dict[str, Any]], semantics: dict[str, Any]) -> list[str]:
    questions = []
    concepts = " ".join(item["ルール軸"] for item in matched)
    if "コストと許可" in concepts:
        questions.append("このカードは通常のコスト制約をどの条件で外しているか。")
    if "誘発と置換" in concepts:
        questions.append("この効果は通常の破壊・移動・ブレイクを置き換えているか。")
    if "終端条件" in concepts:
        questions.append("特殊勝利や追加ターンに必要な前提状態は何か。")
    if "進化元・下敷き" in concepts:
        questions.append("進化元や下敷きの状態が別カードの要求条件になっているか。")
    if semantics.get("constraint_breaks") and semantics.get("special_mechanics"):
        questions.append("制約解除と特殊メカニクスが同一ターン内で連鎖するか。")
    return questions or ["このカードが作る状態を、別カードが要求状態として使えるか。"]
