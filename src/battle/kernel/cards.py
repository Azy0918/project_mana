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
    def is_guardman(self) -> bool:
        return "ガードマン" in self.tags or _keyword_is_static(self.text, "ガードマン")

    @property
    def cannot_attack_player(self) -> bool:
        return "プレイヤーを攻撃できない" in self.text

    @property
    def cannot_attack_creature(self) -> bool:
        """クリーチャーへの攻撃不可(プレイヤーのみ攻撃可)。

        「自分のクリーチャーは〜」の全体付与はグローバル効果で engine が
        モデル外のため除外(exact-safe: 全体付与カードは static 扱いしない)。
        """
        if "クリーチャーを攻撃できない" not in self.text:
            return False
        for clause in re.split(r"[。\n]|■|◇", self.text):
            if "クリーチャーを攻撃できない" not in clause:
                continue
            if any(m in clause for m in _GRANT_CONDITION_MARKERS):
                continue
            if "自分のクリーチャーは" in clause:
                continue
            return True
        return False

    @property
    def cannot_attack(self) -> bool:
        # 「相手プレイヤーを攻撃できない」は部分制限なので全面攻撃禁止とは区別する
        if self.cannot_attack_player:
            return False
        return "攻撃できない" in self.text and "クリーチャーを攻撃できない" not in self.text

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
    def destroy_replacement(self) -> str | None:
        """「破壊されるかわりに〜」の置換先。'mana'/'hand'/'deck_bottom' または None。

        exact-safe: 無条件の置換のみ。条件付き(「自分のターン中」等)は除外。
        """
        text = self.text
        if "かわりに" not in text or ("破壊される" not in text and "破壊された" not in text):
            return None
        for clause in re.split(r"[。\n]|■|◇", text):
            if "かわりに" not in clause or "破壊さ" not in clause:
                continue
            if any(t in clause for t in ("ターン", "なら", "あれば", "次の")):
                continue
            if "マナゾーンに置く" in clause:
                return "mana"
            if "手札に戻す" in clause or "手札に加える" in clause:
                return "hand"
            if "山札の一番下" in clause:
                return "deck_bottom"
        return None

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
    def cannot_summon_from_hand(self) -> bool:
        """手札からの召喚が禁止されているクリーチャー(他手段でのみBZ入場可)。"""
        return (
            "このクリーチャーは召喚できない" in self.text
            or "このクリーチャーは手札から召喚できない" in self.text
        )

    @property
    def cannot_block_evolution(self) -> bool:
        """進化クリーチャーをブロックできない制限。"""
        return "進化クリーチャーをブロックできない" in self.text

    @property
    def cannot_break_shields(self) -> bool:
        """このクリーチャーは攻撃してもシールドをブレイクできない。"""
        return "このクリーチャーはシールドをブレイクできない" in self.text

    @property
    def blocks_owner_strigger(self) -> bool:
        """このクリーチャーの持ち主は「S・トリガー」能力を使えない。"""
        return "自分は「S・トリガー」能力を使えない" in self.text

    @property
    def grants_blocker_to_opponent(self) -> bool:
        """相手のすべてのクリーチャーに無条件で「ブロッカー」を与える静的能力。

        相手が多く守れる=このカードの持ち主にとって不利=engine 模擬は安全側。
        条件付き(なら/につき/ターン等)は範囲を確定できないため除外する。
        """
        for clause in re.split(r"[。\n]|■|◇", self.text):
            if "相手の" not in clause or "ブロッカー" not in clause:
                continue
            if "得る" not in clause and "与える" not in clause:
                continue
            if any(t in clause for t in ("なら", "あれば", "ターン", "につき", "数だけ", "ごとに", "以上", "以下")):
                continue
            if "クリーチャーはすべて" in clause or "すべてのクリーチャー" in clause:
                return True
        return False

    @property
    def self_to_mana_when_summoned_from_hand(self) -> bool:
        """手札から召喚されてBZに出た時、自身をマナゾーンに置く(ルツパーフェ・パンツァー)。"""
        return (
            "自分の手札からバトルゾーンに出た時" in self.text
            and "マナゾーンに置く" in self.text
        )

    @property
    def self_destroy_on_other_evolve(self) -> bool:
        """他のクリーチャーが進化した時、このクリーチャーを破壊する(シャムシャム・カブキリ)。"""
        return "他のクリーチャーが進化した時" in self.text and "このクリーチャーを破壊する" in self.text

    @property
    def battle_both_to_mana(self) -> bool:
        """このクリーチャーがバトルする時、バトル両者をマナに置く(剛勇傀儡ガシガシ)。"""
        return (
            "このクリーチャーがバトルする時" in self.text
            and "バトルするクリーチャー2体をそれぞれマナゾーンに置く" in self.text
        )

    @property
    def block_restriction_race(self) -> str | None:
        """「<種族>以外のクリーチャーはブロックできない」= その種族のみブロック可。

        全プレイヤーに及ぶ静的制限。ブロック可能者が減る=守りが弱くなる方向のみで、
        engine 模擬は安全側。該当しなければ None。
        """
        for clause in re.split(r"[。\n]|■|◇", self.text):
            m = re.match(r"^([ァ-ヶ・ー一-龠]+?)以外のクリーチャーはブロックできない$", clause.strip())
            if m:
                return m.group(1)
        return None

    @property
    def cost_modifier_rule(self) -> dict[str, Any] | None:
        """場にいる間、全プレイヤーの呪文/召喚コストを増やす静的ルール。

        戻り値 dict または None:
          {target: 'spell'|'creature', exclude: civ|None, include: (civ,...)|None,
           mult: int, add: int}
        コスト増加(倍/多くなる)のみ対象。減少は既存の軽減系で扱う。
        コストを増やす方向のみ模擬するため、誤検出しても overcharge=under-model 安全。
        """
        civ = r"(?:光|水|火|闇|自然|無色)"
        for clause in re.split(r"[。\n]|■|◇", self.text):
            if "コストは" not in clause or ("倍" not in clause and "多く" not in clause):
                continue
            obj = r"(呪文を唱える|クリーチャーを召喚する)"
            tail = rf"{obj}コストは(\d+)(倍|多く)"
            exclude = None
            include = None
            m = re.search(rf"({civ})以外の{tail}", clause)
            if m:
                exclude = m.group(1)
                target = "spell" if "呪文" in m.group(2) else "creature"
                n, kind = int(m.group(3)), m.group(4)
            else:
                m = re.search(rf"((?:{civ})(?:または{civ})*)の{tail}", clause)
                if not m:
                    continue
                include = tuple(re.findall(civ, m.group(1)))
                target = "spell" if "呪文" in m.group(2) else "creature"
                n, kind = int(m.group(3)), m.group(4)
            mult = n if kind == "倍" else 1
            add = n if kind == "多く" else 0
            return {"target": target, "exclude": exclude, "include": include,
                    "mult": mult, "add": add}
        return None

    @property
    def enters_tapped(self) -> bool:
        return (
            "タップしてバトルゾーンに出る" in self.text
            or "バトルゾーンにタップして出る" in self.text
        )

    @property
    def no_untap(self) -> bool:
        """アンタップ・ステップでアンタップしない常時の弱点能力。

        text に「アンタップしない / アンタップされない」を含めば真。条件付き・他者付与・
        一時的な「アンタップしない」も保守的に常時アンタップ不可として扱う(=実際より
        強く動くことはない=under-model 安全)。タップしたまま=攻撃もブロックも不可。
        """
        return "アンタップしない" in self.text or "アンタップされない" in self.text

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
