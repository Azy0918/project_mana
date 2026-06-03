from __future__ import annotations

from typing import Any


SPECIAL_COMBO_CONCEPTS: list[dict[str, Any]] = [
    {
        "name": "状態変化",
        "summary": "手札、マナ、墓地、盤面、シールドなどの状態を増減させ、別カードの条件を作る構造。",
        "required_signals": ["ドロー", "マナ加速", "墓地肥やし", "シールド追加", "盤面展開"],
        "why_hard_for_tag_based_ai": "タグは増えたリソースの行き先や、その後どの条件を満たすかまでは表現しにくい。",
        "mana_detection_hint": "state_delta と zones を見て、出力が別カードの入力条件になっているかを見る。",
    },
    {
        "name": "制約解除",
        "summary": "コスト、ゾーン、タイミング、召喚条件などを迂回して通常より早く強い行動へ到達する構造。",
        "required_signals": ["コストを支払わず", "G・ゼロ", "踏み倒し", "超次元", "スピードアタッカー"],
        "why_hard_for_tag_based_ai": "踏み倒しタグだけでは、何の制約をどの条件で破っているかが分からない。",
        "mana_detection_hint": "constraint_breaks に cost_bypass や zone_bypass が出るカードを起点にする。",
    },
    {
        "name": "価値増幅",
        "summary": "1枚のカードや1回の行動から、複数の手札、盤面、マナ、追加行動へ変換する構造。",
        "required_signals": ["複数ドロー", "大量展開", "アンタップ", "もう一度", "連鎖"],
        "why_hard_for_tag_based_ai": "単なるドローや展開タグでは、1枚が何枚分の価値に変換されるかが見えない。",
        "mana_detection_hint": "state_delta が複数ゾーンで正になり、loop_candidate や recursion_candidate を伴うカードを見る。",
    },
    {
        "name": "ループ",
        "summary": "カードの再利用、アンタップ、再詠唱、ゾーン移動により同じ行動を繰り返す構造。",
        "required_signals": ["アンタップする", "唱えてもよい", "手札に戻す", "墓地から手札", "もう一度"],
        "why_hard_for_tag_based_ai": "ループは単体カードではなく、出力が別カードの入力へ戻る循環構造で発生する。",
        "mana_detection_hint": "recursion_candidate と loop_candidate を持つカードをグラフ上で循環接続する。",
    },
    {
        "name": "特殊勝利",
        "summary": "攻撃による通常勝利以外に、手札、シールド、山札、盤面数などの条件で勝つ構造。",
        "required_signals": ["ゲームに勝つ", "手札が10枚以上", "シールドが10枚以上", "山札がなくなるかわり"],
        "why_hard_for_tag_based_ai": "フィニッシャータグだけでは、通常打点と特殊勝利条件を区別できない。",
        "mana_detection_hint": "terminal_effects の extra_win 系を優先的に抽出し、条件達成ルートを探す。",
    },
    {
        "name": "退化",
        "summary": "進化クリーチャーの一番上や下のカードを利用し、想定外のカードを盤面に残す構造。",
        "required_signals": ["進化クリーチャーの下", "一番上", "下に置く", "退化"],
        "why_hard_for_tag_based_ai": "進化タグだけでは、カードの重なりを使ったゾーン・状態操作が見えない。",
        "mana_detection_hint": "evolution_stack と devolution_candidate の両方を持つカード群を見る。",
    },
    {
        "name": "墓地進化",
        "summary": "墓地のカードを進化元や条件として利用し、墓地リソースを盤面へ変換する構造。",
        "required_signals": ["墓地進化", "墓地から進化", "墓地利用", "墓地肥やし"],
        "why_hard_for_tag_based_ai": "墓地利用タグだけでは、墓地が進化条件なのか回収対象なのかが分からない。",
        "mana_detection_hint": "graveyard_evolution と graveyard の state_delta を合わせて見る。",
    },
    {
        "name": "墓地退化",
        "summary": "墓地から進化や重なりを作り、退化によって大型や特殊カードを残す構造。",
        "required_signals": ["墓地", "進化", "退化", "一番上", "下に置く"],
        "why_hard_for_tag_based_ai": "墓地、進化、退化の複合構造なので、単一タグでは見落としやすい。",
        "mana_detection_hint": "graveyard_devolution_candidate と devolution_candidate の共起を見る。",
    },
    {
        "name": "オールデリート系 / リセット系",
        "summary": "盤面、手札、シールド、山札などを大きくリセットし、非対称な勝ち筋へつなげる構造。",
        "required_signals": ["すべて破壊", "すべて墓地", "すべて山札", "オールデリート", "リセット"],
        "why_hard_for_tag_based_ai": "除去タグだけでは、全体リセット後に自分だけが得をする条件を見られない。",
        "mana_detection_hint": "reset_effect と replacement_or_immunity を組み合わせて非対称性を見る。",
    },
    {
        "name": "進化元・下敷き利用",
        "summary": "進化元やカードの下に置かれたカードを、後続効果や退化の材料として使う構造。",
        "required_signals": ["進化元", "下に置く", "下から", "一番上"],
        "why_hard_for_tag_based_ai": "カードがどの位置に重なっているかという状態は、通常タグでは保持されない。",
        "mana_detection_hint": "evolution_stack を持つカードを、devolution_candidate や回収効果と接続する。",
    },
    {
        "name": "ゾーン移動コンボ",
        "summary": "手札、墓地、マナ、山札、超次元などをまたぐ移動で条件や誘発を作る構造。",
        "required_signals": ["手札に戻す", "墓地から", "マナゾーンから", "山札から", "超次元ゾーンから"],
        "why_hard_for_tag_based_ai": "ゾーン移動の前後関係が分からないと、誘発や再利用の接続を見落とす。",
        "mana_detection_hint": "zones と state_delta を使い、from/to の関係を今後の効果グラフへ渡す。",
    },
]


def list_special_combo_concepts() -> list[dict[str, Any]]:
    return SPECIAL_COMBO_CONCEPTS.copy()
