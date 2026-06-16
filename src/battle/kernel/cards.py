from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


_G_ZERO_PATTERN = re.compile(r"G・ゼロ\s*[:：]\s*.*?呪文を(\d+)枚以上唱えたターン")
_G_ZERO_GRAVE_PATTERN = re.compile(r"G・ゼロ\s*[:：]\s*.*?墓地に.*?(\d+)枚以上")
# 「自分のクリーチャー(全体)の召喚コストをN少なくする」無条件オーラだけを拾う。
# 種族・条件・呪文の軽減は適用範囲を検証できないため除外する(exact-safe)。
# 「自分の」の直後がクリーチャーで始まること(=種族プレフィックスなし)を要求し、
# 「魔導具クリーチャー」「NEOクリーチャー」「グランセクトの召喚」等を弾く。
_UNCONDITIONAL_REDUCTION_PATTERN = re.compile(
    r"自分のクリーチャー(?:を|の)召喚(?:する)?コストを(\d+)少なくする"
)
_COST_REDUCTION_PATTERN = re.compile(r"コストを(\d+)少なくする")
# 「なら/あれば/初めて」等の条件付きは無条件オーラと表現が両立しないため除外
_CONDITIONAL_REDUCTION_MARKERS = (
    "なら", "あれば", "初めて", "ごとに", "につき", "数だけ", "枚以上", "枚以下",
    "番目", "能力が書かれていない", "以上で", "以下で", "ターン中",
)

# キーワードが「他者への付与」や「条件付きで得る」文脈のみに現れる場合、
# 自前の無条件静的能力ではないため発動扱いしない(exact-safe)。
_GRANT_CONDITION_MARKERS = (
    "与える", "を得", "を持", "すべて", "なら", "あれば", "以上", "以下",
    "初めて", "ターン", "相手の",
)


def _keyword_is_static(text: str, keyword: str) -> bool:
    """キーワードが「自前の無条件静的能力」として書かれているかを判定する。

    付与(与える/すべて)・条件(なら/あれば/以上)の文脈にしか現れない場合はFalse。
    これにより「クリーチャーにW・ブレイカーを与える」小型カードが自身を
    W・ブレイカー扱いする等の偽陽性を防ぐ(過大評価を避ける=exact-safe)。
    """
    clauses = re.split(r"[。\n]|■|◇", text)
    for clause in clauses:
        if keyword in clause and not any(m in clause for m in _GRANT_CONDITION_MARKERS):
            return True
    return False
_BAD_PATTERN = re.compile(r"B・A・D(?:・S)?\s*(\d+)")


def _parse_power(value: Any) -> int:
    text = str(value or "").strip()
    match = re.search(r"\d+", text)
    if match:
        return int(match.group())
    return 0


def _split_civilizations(value: Any) -> tuple[str, ...]:
    return tuple(civ.strip() for civ in str(value or "").split("/") if civ.strip())


def _split_tags(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple, set)):
        return tuple(tag for tag in value if tag)
    return tuple(tag.strip() for tag in str(value).split(";") if tag.strip())


@dataclass(frozen=True)
class BattleCard:
    card_id: str
    name: str
    civilizations: tuple[str, ...]
    cost: int
    card_type: str
    power: int
    text: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
    race: str = ""

    @property
    def is_creature(self) -> bool:
        if "クリーチャー" in self.card_type:
            return True
        # ツインパクトはパワーを持てばクリーチャー面で運用する
        return "ツインパクト" in self.card_type and self.power > 0

    @property
    def is_spell(self) -> bool:
        return "呪文" in self.card_type

    @property
    def is_blocker(self) -> bool:
        # 他者付与・条件付きブロッカーは自身の常時能力ではないため除外(exact-safe)
        return "ブロッカー" in self.tags or _keyword_is_static(self.text, "ブロッカー")

    @property
    def is_speed_attacker(self) -> bool:
        return "スピードアタッカー" in self.tags or _keyword_is_static(self.text, "スピードアタッカー")

    @property
    def is_mach_fighter(self) -> bool:
        return "マッハファイター" in self.tags or _keyword_is_static(self.text, "マッハファイター")

    @property
    def cannot_attack_player(self) -> bool:
        return "プレイヤーを攻撃できない" in self.text

    @property
    def cannot_attack(self) -> bool:
        # 「相手プレイヤーを攻撃できない」は部分制限なので全面攻撃禁止とは区別する
        if self.cannot_attack_player:
            return False
        return "攻撃できない" in self.text

    @property
    def is_unblockable(self) -> bool:
        # 他者付与・条件付きの「ブロックされない」は自身の常時能力でないため除外
        return _keyword_is_static(self.text, "ブロックされない")

    @property
    def is_multicolor(self) -> bool:
        return len(self.civilizations) > 1

    @property
    def g_zero_spell_count(self) -> int | None:
        """G・ゼロ条件(このターン唱えた呪文の枚数)。なければNone。"""
        match = _G_ZERO_PATTERN.search(self.text)
        if match:
            return int(match.group(1))
        return None

    @property
    def g_zero_grave_count(self) -> int | None:
        """G・ゼロ条件(自分の墓地の枚数)。なければNone。"""
        match = _G_ZERO_GRAVE_PATTERN.search(self.text)
        if match:
            return int(match.group(1))
        return None

    @property
    def bad_discount(self) -> int:
        """B・A・D(コストN軽減で使えるが、ターン終了時に破壊される)。なければ0。"""
        match = _BAD_PATTERN.search(self.text)
        if match:
            return int(match.group(1))
        return 0

    @property
    def summon_cost_reduction(self) -> int:
        """バトルゾーンにいる間、全クリーチャーの召喚コストを下げる量(常時オーラ近似)。

        種族限定・条件付き・呪文専用の軽減は適用範囲を検証できないため除外する
        (exact-safe: 条件を確認できない軽減は省略して過小評価側に倒す。第二十七弾)。
        """
        if not self.is_creature:
            return 0
        match = _UNCONDITIONAL_REDUCTION_PATTERN.search(self.text)
        if not match:
            return 0
        # 同じ文(直前30字)に条件語があれば常時オーラとは扱わない
        clause = self.text[max(0, match.start() - 30):match.start()]
        if any(marker in clause for marker in _CONDITIONAL_REDUCTION_MARKERS):
            return 0
        return int(match.group(1))

    @property
    def power_attacker_bonus(self) -> int:
        # 条件付き・他者付与のパワーアタッカーは常時ボーナスとして扱わない(exact-safe)
        if not _keyword_is_static(self.text, "パワーアタッカー"):
            return 0
        match = re.search(r"パワーアタッカー\s*\+\s*(\d+)", self.text)
        if match:
            return int(match.group(1))
        return 0

    @property
    def attack_power(self) -> int:
        """攻撃時の実効パワー(パワーアタッカー込み)。"""
        return self.power + self.power_attacker_bonus

    @property
    def breaker_count(self) -> int:
        haystack = self.text + ";".join(self.tags)
        # タグは静的能力の確定情報として扱う。テキストは付与/条件文脈を除外する
        if "T・ブレイカー" in self.tags or _keyword_is_static(self.text, "T・ブレイカー"):
            return 3
        if "W・ブレイカー" in self.tags or _keyword_is_static(self.text, "W・ブレイカー"):
            return 2
        if "パワード・ブレイカー" in haystack:
            # パワー6000につき1枚ブレイク(切り上げ)の近似
            return max(1, (self.power + 5999) // 6000)
        return 1

    @property
    def is_charger(self) -> bool:
        """チャージャー呪文: 唱えた後、墓地ではなくマナゾーンに置く。"""
        return self.is_spell and "チャージャー" in self.text

    @property
    def is_slayer(self) -> bool:
        """スレイヤー: バトルした相手クリーチャーをパワーに関係なく破壊する。

        他者付与(「クリーチャーにスレイヤーを与える」)や条件付きは除外する
        (自身が常時スレイヤーである場合のみ=exact-safe)。
        """
        return "スレイヤー" in self.tags or _keyword_is_static(self.text, "スレイヤー")

    @property
    def keyword_grants(self) -> tuple[tuple[str, str | None], ...]:
        """自分のクリーチャー群に常時付与するキーワードのリスト。

        「自分の(すべての)?(<種族>)?クリーチャーは『X』を得る/与える」の無条件オーラのみ。
        戻り: ((keyword, race_filter or None), ...)。exact-safe: 条件付き(なら/あれば/
        ターン/数/につき)は範囲を確定できないため除外する。
        """
        text = self.text
        if "得る" not in text and "与える" not in text:
            return ()
        grants: list[tuple[str, str | None]] = []
        for clause in re.split(r"[。\n]|■|◇", text):
            if "自分の" not in clause or ("得る" not in clause and "与える" not in clause):
                continue
            if any(t in clause for t in ("なら", "あれば", "ターン", "につき", "数だけ", "ごとに", "以上", "以下")):
                continue
            for kw in ("スピードアタッカー", "ブロッカー", "スレイヤー", "マッハファイター"):
                if f"「{kw}」" in clause or kw in clause:
                    m = re.search(r"自分の(?:すべての)?(?:([ァ-ヶ・ー一-龠]+?)(?:の|は|に))", clause)
                    race = None
                    if m and m.group(1) not in ("クリーチャー", "すべて"):
                        race = m.group(1)
                    grants.append((kw, race))
        return tuple(dict.fromkeys(grants))

    @property
    def enters_tapped(self) -> bool:
        return "タップしてバトルゾーンに出る" in self.text

    @property
    def is_shield_burner(self) -> bool:
        """ブレイクしたシールドを手札に加えさせず墓地に置かせる。"""
        return "手札に加えるかわりに墓地に置く" in self.text

    @property
    def spell_lock(self) -> tuple[str | None, int | None, bool] | None:
        """このクリーチャーがいる間、「誰も」呪文を唱えられなくする静的ロックの仕様。

        戻り値 (civ_keep, max_cost, requires_tapped) または None。
        - civ_keep: この文明の呪文は許可(「光以外」→'光')。Noneなら全文明を禁止
        - max_cost: このコスト以下の呪文のみ禁止。Noneなら全コスト
        - requires_tapped: このクリーチャーがタップ状態のときのみ有効(お騒がせチューザ)

        exact-safe: 「誰も〜呪文を唱えられない」の無条件/タップ条件のみを拾う。
        タイミング限定(「そのターン」「次の…ターン」)・回数制限(「一度しか」)・
        条件付き(「ラビリンス」「〜なら」)・「相手は」限定の一時効果は、静的な範囲を
        確定できないため除外する。
        """
        text = self.text
        if "呪文を唱えられない" not in text:
            return None
        for clause in re.split(r"[。\n]|■|◇", text):
            if "呪文を唱えられない" not in clause or "誰も" not in clause:
                continue
            if any(m in clause for m in ("そのターン", "次の", "ターン中", "一度", "ラビリンス", "なら", "あれば")):
                continue
            civ_keep = None
            m = re.search(r"(光|水|火|闇|自然)以外の呪文", clause)
            if m:
                civ_keep = m.group(1)
            max_cost = None
            mc = re.search(r"コスト(\d+)以下の呪文", clause)
            if mc:
                max_cost = int(mc.group(1))
            requires_tapped = "タップしている時" in clause or "タップしているとき" in clause
            return (civ_keep, max_cost, requires_tapped)
        return None

    @property
    def disables_broken_strigger(self) -> bool:
        """このクリーチャーがブレイクしたシールドのS・トリガーを相手が使えなくする。

        「(相手は)このクリーチャーがブレイクしたシールドの『S・トリガー』を使えない」型
        (per-break・攻撃者依存)を検出する。生き残らずとも攻撃時に受けを無効化する
        ため、静的ロックより反S・トリガー性能が高い。種族トーテム限定や条件付きは
        範囲を静的確定できないため除外(exact-safe)。
        """
        if "ブレイク" not in self.text or "S・トリガー" not in self.text:
            return False
        return bool(
            re.search(
                r"この(?:クリーチャー)?がブレイクしたシールドの「?S・トリガー」?[^。]*?使えない",
                self.text,
            )
        )

    @property
    def strigger_lock_civs(self) -> tuple[str, ...]:
        """このクリーチャーがいる間、指定文明のS・トリガーを誰も使えなくする文明の一覧。

        「誰も(の)〜のカードの『S・トリガー』を使えない」の無条件・全体ロックのみを
        拾う(exact-safe)。条件付き(「〜なら/あれば」)や、自分の攻撃でブレイクした
        シールド限定の per-break 型(「このクリーチャーがブレイクした〜」)は、適用
        範囲を静的に確定できないため除外し、過大評価を避ける。
        """
        if "S・トリガー" not in self.text or "使えない" not in self.text:
            return ()
        civs: list[str] = []
        for match in re.finditer(
            r"誰も[^。]{0,4}(光|水|火|闇|自然)のカード[^。]*?S・トリガー[^。]*?使えない",
            self.text,
        ):
            clause_start = self.text.rfind("。", 0, match.start()) + 1
            clause = self.text[clause_start : match.end()]
            if any(marker in clause for marker in ("なら", "あれば", "以上", "以下", "ブレイクした")):
                continue
            civs.append(match.group(1))
        return tuple(dict.fromkeys(civs))

    @property
    def is_evolution(self) -> bool:
        """進化クリーチャー: 召喚酔いしない。

        進化元は engine.can_play_evolution が「味方クリーチャー1体以上」で近似要求し、
        召喚時に最弱の味方1体を消費する(進化元の種族・文明条件はデータ不足のため省略)。
        表記ゆれ対応: 「進化:」「進化-」「進化V-」「墓地進化-」等。
        """
        if "進化" in self.card_type:
            return True
        return bool(re.search(r"進化(V|GV)?\s*[:：\-−–-]", self.text))


def battle_card_from_dict(card: dict[str, Any]) -> BattleCard:
    card_type = str(card.get("card_type", ""))
    power = _parse_power(card.get("power"))
    cost = int(card.get("cost") or 0)
    # データ品質対策: コスト0登録のツインパクトはパワーからコストを推定する
    # (実カードにコスト0は存在せず、放置すると毎ターン無償プレイになるため)
    if cost <= 0 and "ツインパクト" in card_type:
        cost = max(2, power // 1000)
    return BattleCard(
        card_id=str(card.get("card_id", "")),
        name=str(card.get("name", "")),
        civilizations=_split_civilizations(card.get("civilization")),
        cost=cost,
        card_type=card_type,
        power=power,
        text=str(card.get("text", "") or ""),
        tags=_split_tags(card.get("tags")),
        race=str(card.get("race", "") or ""),
    )


def battle_deck_from_dicts(deck: list[dict[str, Any]]) -> list[BattleCard]:
    cards: list[BattleCard] = []
    for entry in deck:
        quantity = int(entry.get("quantity", 1))
        card = battle_card_from_dict(entry)
        cards.extend([card] * quantity)
    return cards
