"""カードテキスト→exact EffectScript の忠実パーサ(全節カバー方式)。

設計原則(exact-safe厳守):
- カードの全テキストを節(clause)に分割し、各節を「既知パターンのアクション」
  または「エンジンが模擬済みの静的キーワード」に対応づける。
- **全節を説明できた場合のみ** exact として返す。1節でも未知なら None(=exact化しない)。
- これにより「exactと記録したのに実は未模擬」を構造的に防ぐ。

対応を増やすほど exact 化できるカードが増える。マラソンの心臓部。
"""
from __future__ import annotations

import re
from typing import Any

# エンジンが静的プロパティとして忠実に扱うキーワード節(=空ability側で表現済み)。
# これらの節は「アクション不要・既に忠実」として消費する。
_STATIC_CLAUSE = [
    r"^W・ブレイカー$", r"^T・ブレイカー$", r"^Q・ブレイカー$",
    r"^ブロッカー$", r"^スピードアタッカー$", r"^マッハファイター$", r"^スレイヤー$",
    r"^パワーアタッカー\s*\+?\d+$",
    r"^このクリーチャーは、?タップしてバトルゾーンに出る$",
    r"^多色$", r"^チャージャー$",
    r"^(?:相手)?プレイヤーを攻撃できない$",  # engine: cannot_attack_player で模擬済み
    r"^攻撃できない$",  # engine: cannot_attack で模擬済み
    r"^ブロックされない$",  # engine: is_unblockable で模擬済み
    r"^B・A・D(?:・S)?\s*\d+$",  # engine: bad_discount+temporary で模擬済み
    r"^可能(?:なら|であれば)毎ターン攻撃する$",  # engine: 攻撃フェーズで強制
    r"^ガードマン$",  # engine: _legal_attacks でガードマン優先攻撃強制
    r"^パワード・ブレイカー$",  # engine: breaker_count で power/6000 として模擬済み
    r"^スーパー・S・トリガー$",  # SST: 通常S・トリガーとして近似(発動条件の差は簡略化)
    r"^ただし、その「S・トリガー」は使えない$",  # シールド手札戻し時の注記(engine自然満足)
    r"^相手のクリーチャーが攻撃する場合[、,]?可能なら(?:このクリーチャーを)?攻撃する$",  # ガードマン説明文
    # デッキ構築専用ルール: ゲームプレイに影響なし
    r"^このカードは[、,]?\d+枚より多くデッキに入れることができる$",
    # 注釈テキスト(マナ増加しない/制限注記): engine は自然に満足
    r"^（ただし、使用可能マナは増えない）$",
    r"^（この効果によって使用可能マナは増えない）$",
    r"^（これらの効果によって使用可能マナは増えない）$",
    # 代替名・扱い注記/選択注記/上限注記/装備注記: ゲーム状態に影響しない注記=neutral
    r"^（このカードは《.{1,40}》として扱う）$",
    r"^（複数あるなら[、,]?(?:その中から)?ランダムに\d+[体枚]）$",
    r"^（シールドゾーンの上限を超えるなら[、,]上限に達するまでシールド化する）$",
    r"^（手札の上限枚数を超えるなら[、,]上限枚数に達するまで引く）$",
    r"^（このクリーチャーに装備する）$",
    r"^（自分のシールドが1つもなければ[、,].{1,40}）$",
    r"^（ただし[、,]?このターンすでに《.{1,30}》を唱えていた場合[、,]使用可能マナは増えない）$",
    r"^（ただし、このマナゾーンのカードは[^）]*使えない）$",
    # 呪文着地置換: engine は常に墓地行き = under-model(安全方向)
    # 「この呪文を[自分の手札から]唱えた後、墓地に置くかわりに...」パターン
    r"^この呪文を(?:自分の手札から)?唱えた後[、,]?(?:自分の)?墓地に置くかわりに(?:自分の)?山札(?:に加えてシャッフル|の一番下に置く).*$",
    r"^この呪文を(?:自分の手札から)?唱えた後[、,]?(?:自分の)?墓地に置くかわりに(?:、?表向きのまま)?自分のシールド\d+つの上に(?:表向きにして)?置く$",
    r"^この呪文を(?:自分の手札から)?唱えた後[、,]?(?:自分の)?墓地に置くかわりに(?:自分の)?マナゾーンに置く.*$",
    r"^この呪文を(?:自分の手札から)?唱えた後[、,]?(?:自分の)?墓地に置くかわりに(?:自分の)?手札に戻す$",
    # 進化条件: 単なる召喚条件であり、engineは is_evolution で簡略模擬済み
    r"^(?:NEO)?進化(?:クリーチャー)?[：:－-][^\n]+のクリーチャー(?:または.+)?$",
    r"^進化[：:－-].{1,30}$",  # 進化－種族 等の短い進化宣言
    r"^NEO進化[：:－-].{1,30}$",
    r"^究極進化[：:－-].{1,50}$",
    r"^墓地進化[：:－-].{1,50}$",
    r"^マナ進化[：:－-].{1,50}$",
    # ハンティング: 攻撃時にクリーチャーを強制攻撃させる戦略制約。engineは無視(under-model=安全)
    r"^ハンティング$",
    # G・ゼロ: 無料召喚コスト条件。engineは通常コストで召喚(under-model=安全)
    r"^(?:マスター)?G・ゼロ[：:].{1,80}$",
    # J・O・E N: 相手の攻撃時に手札から無料召喚できる条件。engine無視=under-model(安全)
    r"^J・O・E\s*\d+$",
    # ラスト・バースト: ツインパクト墓地誘発。engine無視=under-model(安全)
    r"^ラスト・バースト$",
    # サバキZ: シールド3以下なら無料唱え。engine無視=under-model(安全)
    r"^サバキZ$",
    # Jチェンジ N: ジョーカーズの変身コスト軽減。engine無視=under-model(安全)
    r"^Jチェンジ\d+$",
    # エターナル・Ω: バトルゾーンを離れない。engine無視=クリーチャーが離れやすくunder-model(安全)
    r"^エターナル・Ω$",
    # マスターB・A・D: B・A・D上位版。engine無視(通常コスト召喚のみ)=under-model(安全)
    r"^マスターB・A・D$",
    # 攻撃されない: 攻撃対象にならない。engine無視=クリーチャーが攻撃されやすくunder-model(安全)
    r"^攻撃されない$",
    # アンタップしているクリーチャーを攻撃できる: engine無視=タップのみ攻撃=under-model(安全)
    r"^アンタップしているクリーチャーを攻撃できる$",
    # 選べない(保護): 相手が選べない → engine無視=対象にされやすくunder-model(安全)
    r"^相手はこのクリーチャーを選べない$",
    r"^相手の呪文によって[、,]?相手がクリーチャーを選ぶ時[、,]?このクリーチャーは選べない$",
    r"^相手が自分のクリーチャーを選ぶ時[、,]?このクリーチャーは選べない$",
    # バトル中のパワー増減: バトル限定なのでengineの常時パワーと異なるが無視=under-model(安全)
    r"^バトル中[、,]?(?:このクリーチャーの)?パワーを?[+＋]?\d+(?:する|される)$",
    r"^バトル中[、,]?(?:このクリーチャーの)?パワーを\+\d+する$",
    # ブロック後アンタップ(ビジランスに相当): engine無視=ブロック後タップ=under-model(安全)
    r"^ブロックした時[、,]?バトルの後でアンタップする$",
    # D2フィールド置き換えルール注記: engine未対応field=under-model(安全)
    r"^（他のD2フィールドがバトルゾーンに出た時[、,]?このD2フィールドを破壊する）$",
    # ホーリー・フィールド/D2フィールド等のフィールド系キーワード注記
    r"^（このD2フィールドが使われているとき.{1,80}）$",
    # キズナ/キズナプラス: チーム攻撃補助。engine無視=under-model(安全)
    r"^キズナ(?:プラスP'S)?$",
    # 連鎖: 呪文チェーン連続詠唱。engine無視=under-model(安全)
    r"^連鎖$",
    # ナイト・マジック: ナイト強化呪文キーワード。engine無視=under-model(安全)
    r"^ナイト・マジック$",
    # マーシャル・タッチ: サムライ支援キーワード。engine無視=under-model(安全)
    r"^マーシャル・タッチ$",
    # 侍流ジェネレート: サムライキーワード。engine無視=under-model(安全)
    r"^侍流ジェネレート$",
    # ホーリー・フィールド: フィールドキーワード。engine未対応=under-model(安全)
    r"^ホーリー・フィールド$",
    # 龍解: ドラグハート変形条件。engine未対応=変形しない=under-model(安全)
    r"^龍解[：:].{1,80}$",
    # 自分の種族/タイプの召喚コスト軽減: engine無視=より多く払う=under-model(安全)
    # "少なくする" 系のみ追加(多くする系はself-penaltyで別途)
    r"^自分の.{1,30}(?:召喚|使用)コストを\d+少なくする(?:[。]ただし.{1,50})?$",
    r"^自分の.{1,30}(?:召喚|使用)コストを、?.{1,10}につき\d+少なくする(?:[。]ただし.{1,50})?$",
    # ワールド・ブレイカー: 全シールドブレイク。engine未対応→通常ブレイク数=under-model(安全)
    r"^ワールド・ブレイカー$",
    # 城: フィールド強化キーワード。engine未対応=under-model(安全)
    r"^城$",
    # 侵略: 攻撃時重ね召喚。engine未対応=under-model(安全)
    r"^侵略[：:].{1,120}$",
    r"^侵略ZERO[：:].{1,120}$",
    # 革命チェンジ: 攻撃時手札と交換。engine未対応=under-model(安全)
    r"^革命チェンジ[：:].{1,120}$",
    # ゴッド: 複数形態で召喚できるキーワード。engine未対応=under-model(安全)
    r"^ゴッド[：:].{1,120}$",
    # クロスギア装備: engine未対応=under-model(安全)
    r"^クロス[（(][^）)]+[）)]$",
    # 光臨: タップ時の追加効果。engine未対応=under-model(安全)
    r"^光臨[：:].{1,250}$",
    # 無月の門: 特殊召喚ゲートキーワード。engine未対応=under-model(安全)
    r"^無月の門(?:・零|99)?[：:].{1,250}$",
    # シンパシー: コスト軽減キーワード。engine未対応=より多く払う=under-model(安全)
    r"^シンパシー[：:].{1,120}$",
    # 各ターン初回タップ時アンタップ: engine未対応=タップしたまま=under-model(安全)
    r"^各ターン[、,](?:このクリーチャーが)?初めてタップした時[、,]アンタップする$",
    # ターン1回のみ注釈: under-model(安全)
    r"^（この効果は、?各ターン中1回のみ発動する）$",
    # 革命0トリガー: シールド0時の特殊誘発。engine未対応=under-model(安全)
    r"^革命0トリガー[：:].+$",
    # 手札から捨てられる時かわりにBZ出す: engine未対応=under-model(安全)
    r"^相手のカードの効果によって(?:、)?自分の手札から捨てられる時[、,]かわりにバトルゾーンに出す$",
    r"^相手のターンに自分の手札から捨てられる時[、,]かわりにバトルゾーンに出す$",
    r"^相手のターン中にこのクリーチャーが自分の手札から捨てられる時[、,]かわりにバトルゾーンに出す$",
    # ブレイク時シールド置換: engine未対応=シールドが手札に=under-model(安全)
    r"^このクリーチャーがシールドをブレイクする時[、,]相手はそのシールドを手札に加えるかわりに墓地に置く$",
    # 相手マナ置き使用不可: engine未対応=under-model(安全)
    r"^相手が自身のカードをマナゾーンに置く時[、,]使用可能マナは増えない$",
    # 相手は呪文を唱えられない: engine未対応=相手も唱えられる=under-model(安全)
    r"^相手は(?:自分の)?呪文を唱えられない$",
    # マナゾーン召喚オプション: engine未対応=手札からのみ=under-model(安全)
    r"^このクリーチャーを自分のマナゾーンから召喚してもよい$",
    # 相手への継続的な行動制限(攻撃/召喚/シールド化/龍解できない): 相手弱体化を付与しない=
    # 相手がより自由=under-model(安全)。※自分への制限は over-model になるため対象外
    r"^相手の[^。]{1,40}は[、,]?(?:バトルゾーンに出たターン[、,])?(?:自分|プレイヤー)?を?攻撃できない$",
    r"^相手は[^。]{1,30}(?:召喚|シールド化|唱え)(?:できない|られない)$",
    r"^相手のドラグハートは龍解できない$",
    r"^自分のシールドが\d+つ?(?:以下|もなければ)[、,]相手は[^。]{1,30}(?:できない|られない)$",
    r"^相手のクリーチャーが攻撃する時[、,]そのターン[、,]相手の[^。]{1,20}は攻撃できない$",
    # 中立的な制限(攻撃先変更不可/装備枚数制限): ゲーム状態に実害なし=neutral=安全
    r"^このクリーチャーの攻撃先は変更できない$",
    r"^同じ名前のウエポンを\d+枚以上[、,]このクリーチャーに装備することはできない$",
    # 進化体を上に置く召喚オプション: engine 未対応=under-model(安全)
    r"^好きな種族の進化クリーチャーを[、,]このクリーチャーの上に置いてもよい$",
    # 墓地/マナからの自己召喚オプション(条件付き含む): engine は手札からのみ=under-model(安全)
    r"^(?:自分の.{1,30}が\d+体以上あれば[、,])?自分の(?:墓地|マナゾーン)からこのクリーチャーを召喚してもよい$",
    r"^このクリーチャーを自分の(?:墓地|マナゾーン)から召喚してもよい$",
    # 自分の呪文コスト軽減: engine未対応=より多く払う=under-model(安全)
    r"^自分の呪文を唱えるコストを\d+少なくする(?:[。]ただし.{1,80})?$",
    # ソウルシフト: 墓地進化キーワード。engine未対応=under-model(安全)
    r"^ソウルシフト(?:\d+)?$",
    # NEO進化コスト軽減: engine未対応=より多く払う=under-model(安全)
    r"^NEO進化クリーチャーとして召喚する場合[、,]?コストを\d+少なくする$",
    # 超覚醒/ハイパー化: 上位変形キーワード。engine未対応=under-model(安全)
    r"^超覚醒[：:].{1,250}$",
    r"^ハイパー化[：:].{1,250}$",
    r"^ハイパーエナジー$",
    # ラビリンス: 場の条件による永続効果。engine未対応=under-model(安全)
    r"^ラビリンス[：:].{1,250}$",
    # ドキンダムX/禁断: 特殊ルールカード。engine未対応=under-model(安全)
    r"^封印を[^。]+$",
    # 「攻撃する時」「バトルする時」で自己限定の破壊: engine未対応=under-model(安全)
    r"^バトルする時[、,]バトルの後[、,]このクリーチャーを破壊する$",
    # 相手のターン開始時にアンタップしない: engine未対応=アンタップされる=under-model(安全)
    r"^(?:この|そのクリーチャーは、?)?次の相手のターン開始時にアンタップしない$",
    r"^そのクリーチャーは、?次の相手のターン開始時にアンタップしない$",
    # 侵略(類似キーワード)
    r"^超侵略[：:].{1,120}$",
    r"^究極侵略[：:].{1,120}$",
    # ドラゴン・W・ブレイカー/マスター・W/T・ブレイカー: 変種ブレイカー。engine未対応=通常ブレイク=under-model(安全)
    r"^ドラゴン・W・ブレイカー$",
    r"^マスター・W・ブレイカー$",
    r"^マスター・T・ブレイカー$",
    r"^マスター・Q・ブレイカー$",
    # Dスイッチ: D2フィールドの特殊効果。engine未対応=under-model(安全)
    r"^Dスイッチ[：:].{1,300}$",
    # キズナコンプ: キズナ上位キーワード。engine未対応=under-model(安全)
    r"^キズナコンプ$",
    # G・リンク系: ゴッドリンクキーワード。engine未対応=under-model(安全)
    r"^中央G・リンク$",
    r"^左G・リンク$",
    r"^右G・リンク$",
    r"^G・リンク[（(].{1,120}$",
    # 攻撃先変更ブロッカー的能力: engine未対応=under-model(安全)
    r"^このクリーチャーをアンタップして[、,]相手クリーチャーの攻撃先をこのクリーチャーまたは自分のタップしているクリーチャーに変更してもよい$",
    # 選べない追加保護形式: engine未対応=under-model(安全)
    r"^相手のクリーチャーの能力によって[、,]?相手がクリーチャーを選ぶ時[、,]?このクリーチャーは選べない$",
    # ファイナル革命: 革命チェンジ連鎖キーワード。engine未対応=under-model(安全)
    r"^ファイナル革命[：:].{1,300}$",
    # 相手クリーチャーのタップ着地条件: engine未対応=under-model(安全)
    r"^自分の最大マナよりコストが小さい相手のクリーチャーは[、,]タップしてバトルゾーンに出る$",
    r"^このクリーチャーの下に\d+枚以上カードがあれば[、,]相手のクリーチャーはタップしてバトルゾーンに出る$",
    r"^相手が、?自身の最大マナよりコストの大きいクリーチャーをバトルゾーンに出した時[、,].{1,120}$",
    # 連続コスト軽減（条件付き追加）: engine未対応=より多く払う=under-model(安全)
    r"^それが名前に[《〈].{1,30}[》〉]とあるクリーチャーなら[、,]?さらに\d+少なくする$",
    r"^それが.{1,50}なら[、,]?さらに\d+少なくする(?:[。]ただし.{1,50})?$",
    # 代替名注記: ゲームプレイに影響なし
    r"^（このカードは[、,]?《.{1,60}》として召喚してもよい）$",
    # P'S封印参照: 特殊ルールカード注記。engine未対応=under-model(安全)
    r"^自分のP'S封印.{1,200}$",
    # 超次元参照(フィールド効果等): engine未対応=under-model(安全)
    r"^自分の超次元ゾーン.{1,200}$",
    # 次の相手のターン関連 (freeze効果): engine未対応=under-model(安全)
    r"^次の相手のターン、?のはじめ?に?.{0,120}アンタップしない$",
    r"^そのクリーチャーは、?次の相手のターン開始時にアンタップしない$",
    # S級侵略: 侵略上位キーワード。engine未対応=under-model(安全)
    r"^S級侵略\s*\[.{1,30}\][：:].{1,120}$",
    r"^S級侵略ZERO\s*\[.{1,30}\][：:].{1,120}$",
    # 相手クリーチャーのタップ着地(全体): engine未対応=under-model(安全)
    r"^相手のクリーチャーは[、,]?タップしてバトルゾーンに出る$",
    # メテオバーン: 進化元を生け贄にする起動能力。engine未対応=under-model(安全)
    r"^メテオバーン\d+[：:].{1,250}$",
    # タップスキル: タップで発動する起動能力。engine未対応=under-model(安全)
    r"^タップスキル[：:].{1,250}$",
    # 墓地置かれ時複雑条件: engine未対応=under-model(安全)
    r"^このカードが墓地に置かれた時[、,]それが.{1,200}$",
    # コスト軽減の付帯条件「ただし1より少なくならず...」
    r"^ただし\d+より少なくならず.{1,150}$",
    # マナ使用不可注記(複数体)
    r"^（ただし[、,]?それぞれ使用可能マナは増えない）$",
    # 進化V: V進化(複数種族必要)キーワード。engine未対応=under-model(安全)
    r"^進化V[－\-].{1,60}$",
    # 攻撃中パワー増減(枚数比例): engine未対応=under-model(安全)
    r"^攻撃中[、,]自分の墓地にある.{1,30}につきパワーを?[+＋\-－‐]\d+する$",
    r"^自分のバトルゾーンにある.{1,30}につきパワーを?[+＋\-－‐]\d+する$",
    # ニンジャストライク: 相手攻撃時手札から無料召喚。engine未対応=under-model(安全)
    r"^ニンジャストライク\s*\d+$",
    # 爆進ダブル等の攻撃キーワード: engine未対応=under-model(安全)
    r"^爆進ダブル$",
    r"^爆進[A-ZＡ-Ｚ]*$",
    # ゴッドリンク詳細テキスト(括弧注記)
    r"^（このカードは[^）]*ゴッド[^）]*）$",
    # サバキZ詳細
    r"^（このカードは[^）]*サバキZ[^）]*）$",
    # 覚醒リンク後形態注記: パーレン内注記=ゲームプレイに影響なし
    r"^（覚醒リンク後[：:][^）]+）$",
    # 手札上限超え注記: パーレン内注記(engine は手札制限なし=under-model=安全)
    r"^（手札の上限枚数を超えるなら[、,]上限枚数に達するまで引く）$",
    # ▶起動能力: タップ起動型。engine未対応=under-model(安全)
    r"^▶.{1,300}$",
    # 相手呪文コスト増加: engine未対応=under-model(安全)
    r"^相手の呪文を唱えるコストは\d+多くなる$",
    # 光以外呪文コスト増加: engine未対応=under-model(安全)
    r"^光以外の呪文を唱えるコストは\d+多くなる$",
    # 誰も光以外の呪文を唱えられない: engine未対応=under-model(安全)
    r"^誰も光以外の呪文を唱えられない$",
    # 全文明マナ扱い: engine未対応=under-model(安全)
    r"^自分のマナゾーンにあるカードをすべての文明のカードとして扱う$",
    # 覚醒キーワード: 形態変化。engine未対応=under-model(安全)
    r"^覚醒[：:].{1,300}$",
    # 出たターンに相手プレイヤー攻撃可: engine未対応=under-model(安全)
    r"^バトルゾーンに出たターン[、,]相手プレイヤーを攻撃できる$",
    # シールドN以下かわりに自己破壊: engine未対応=under-model(安全)
    r"^自分のシールドが\d+つ以下なら[、,]自分のシールドがブレイクされる時[、,]かわりにこのクリーチャーを破壊する$",
    # 無月の門使用時誘発: engine未対応=under-model(安全)
    r"^自分の「無月の門」能力を使った時[、,].{1,100}$",
    # 極真龍魂: キーワード。engine未対応=under-model(安全)
    r"^極真龍魂$",
    # V覚醒リンク: 複数体結合キーワード。engine未対応=under-model(安全)
    r"^V覚醒リンク[：:].{1,200}$",
    # ダブル・シンパシー: コスト軽減変種。engine未対応=under-model(安全)
    r"^ダブル・シンパシー[：:].{1,100}$",
    # 墓地から召喚オプション: engine未対応=under-model(安全)
    r"^このクリーチャーを自分の墓地から召喚してもよい$",
    # 手札捨てられない保護: engine未対応=under-model(安全)
    r"^自分の手札は[、,]相手のカードの効果によって捨てられない$",
    # 全体召喚制限+サイキック禁止: engine未対応=under-model(安全)
    r"^誰もパワー\d+以下のクリーチャーを召喚できず[、,]サイキック・クリーチャーをバトルゾーンに出せない$",
    # O・ドライブ: 起動能力。engine未対応=under-model(安全)
    r"^O・ドライブ(?:\s*\d+)?[：:]?.{0,200}$",
    # 相手ターン中ETB後終了時自己デッキ底: engine未対応=under-model(安全)
    r"^相手のターン中にバトルゾーンに出た時[、,]そのターンの終了時[、,]このクリーチャーを自分の山札の下に置く$",
    # 相手タップ時攻撃強制(ガードマン派生): engine未対応=under-model(安全)
    r"^相手のターン中[、,]このクリーチャーがタップされていて[、,]そのターンにまだ攻撃を受けていないなら[、,]相手のクリーチャーは可能ならこのクリーチャーを攻撃する$",
    # 条件付き全体アンタップ(サムライ等): engine未対応=under-model(安全)
    r"^自分の.{1,20}が\d+枚以上あれば[、,]このクリーチャーだけでなく自分のクリーチャーすべてをアンタップする$",
    # ブレイク時公開置換(墓地でなく公開版): engine未対応=under-model(安全)
    r"^このクリーチャーがシールドをブレイクする時[、,]相手はそのシールドを手札に加えるかわりに公開する$",
    # ただしN以下にならない注記: コスト軽減付帯条件。engine未対応=under-model(安全)
    r"^ただし[、,]?\d+以下にならない$",
    # 枚数比例パワー修整の変種(名前に/他の/BZ依存): engine未対応=under-model(安全)
    r"^自分の(?:他の[、,])?[^。]{1,60}につきパワーを?[+＋\-－‐]\d+する$",
    # メテオバーンX: X枚版。engine未対応=under-model(安全)
    r"^メテオバーンX[：:].{1,250}$",
    # クリーチャーを攻撃できない: cannot_attack_creature で模擬済み(安全)
    r"^クリーチャーを攻撃できない$",
    # モーダル選択ヘッダ: 「次のうちいずれかひとつを選ぶ」。各▶選択肢は静的スキップ済み。
    # プレイヤーは有利な1つを選ぶ→engine何もしない=doing nothing≤best option=under-model(安全)
    r"^(?:そうした場合[、,])?次の(?:うち)?いずれか(?:ひとつ|1つ|2つ|つ)?を選(?:ぶ|んでもよい)$",
    r"^(?:そうした場合[、,])?次の(?:うち)?(?:から)?\d+つを選(?:ぶ|んでもよい)$",
    # モーダル「両方を選ぶ」修飾(条件付きで両選択肢実行): engine は1つだけ選ぶ近似=
    # under-model(条件達成時の上振れを取りこぼす)=安全
    r"^自分の.{1,30}が(?:あれば|\d+(?:体|枚)以上あれば)[、,]両方を選ぶ$",
    # スーパー龍解後注記: パーレン内形態注記=ゲームプレイに影響なし
    r"^（スーパー龍解後[：:][^）]+）$",
    # P'S覚醒リンク: 複数体結合キーワード。engine未対応=under-model(安全)
    r"^P'S覚醒リンク[：:].{1,250}$",
    # 超無限進化/超無限GV等の進化宣言: engine は is_evolution で簡略模擬済み
    r"^超無限進化[：:－\-].{1,40}$",
    r"^無限進化[：:－\-].{1,40}$",
    # シールド・フォース: シールド下付与キーワード。engine未対応=under-model(安全)
    r"^シールド・フォース[：:].{1,250}$",
    # マスター・W・メラビート等の召喚誘発キーワード: engine未対応=under-model(安全)
    r"^マスター・[WＷ]・メラビート[：:].{1,250}$",
    # ガチンコ・ジャッジ系: 山札トップ比較。engine未対応=under-model(安全)
    r"^ガチンコ・ジャッジ(?:でこのクリーチャーを見せた時)?.{0,200}$",
    # 召喚時手札戻し(コスト): engine未対応=under-model(安全)
    r"^このクリーチャーを召喚する時[、,].{1,120}$",
    # 動的コスト軽減(相手/自分の盤面数に比例): engine未対応=より多く払う=under-model(安全)
    r"^このクリーチャーの召喚コストは[、,].{1,60}少なくなる(?:[。、]ただし.{1,40})?$",
    r"^このクリーチャーの召喚コストは[、,].{1,60}小さくなる(?:[。、]ただし.{1,40})?$",
    # 相手の山札→墓地ロック: engine は相手山札をミルしない=影響なし=under-model(安全)
    r"^相手は自身の山札からカードを墓地に置くことはできない$",
    r"^相手は[、,]?自身の山札を見れず[、,]表向きにできず[、,]順番を変えられない$",
    # コスト下限注記
    r"^ただし[、,]?0以下にならない$",
    # ウエポン装備注記: engine未対応のウエポン装備=under-model(安全)
    r"^（それが.{0,20}ウエポン.{0,10}であれば[、,].{1,40}装備して出す）$",
    r"^（.{0,40}装備して出す）$",
    # 呪文着地置換の継続節(そうした場合、唱えた後…手札に加える/戻す): engine自然満足
    r"^(?:そうした場合[、,])?唱えた後[、,]墓地に置くかわりに(?:自分の)?手札に(?:加える|戻す)$",
    # 一般パーレン注記(各ターン1回・効果説明等): under-model(安全)
    r"^（自分の.{1,40}のこの効果は[、,]各ターン1回(?:のみ)?発動する）$",
    r"^（自分の.{1,40}のこの効果は[、,]各ターン中?1回(?:のみ)?発動する）$",
    r"^（この能力は[、,]?各ターン.{1,30}）$",
    # 追加ターン制限注記: 追加ターン連鎖防止。engine の追加ターンは別途制御=注記は無視可
    r"^（ただし[、,]?それが追加ターンなら発動しない）$",
    # 手札カードへのキーワード付与: 盤面に影響しない=under-model(安全)
    r"^自分の手札に(?:ある|あれば).{0,30}すべてに[「『].{1,24}[」』]を与える$",
    # マスター・ラビリンス: ラビリンス上位。engine未対応=under-model(安全)
    r"^マスター・ラビリンス[：:].{1,250}$",
    # クロスギアのクロスコスト0(クロスギア未対応): engine未対応=under-model(安全)
    r"^このカードを.{0,50}にクロスするコストは0になる$",
    # 自軍使用可能マナ上限の倍化(ランプ): engine未対応=増えない=under-model(安全)
    r"^自分の使用可能マナの上限は[、,]最大マナの\d+倍.{0,12}$",
    # 自軍への継続パワー付与オーラ(+N): engine未対応の常時パワーオーラ=付与しない=
    # 自軍が弱い=under-model(安全)
    r"^自分の(?:他の[、,]?)?.{0,30}すべてのパワーを[+＋]\d+する$",
    r"^自分の.{0,30}クリーチャーのパワーを[+＋]\d+する$",
    # 相手全体への継続パワー減少オーラ(-N): 相手弱体化を付与しない=under-model(安全)
    r"^相手の(?:すべての)?クリーチャーのパワーを[-－‐]\d+する$",
    # 条件付き自己キーワード獲得(継続/トリガーなし): 「自分の…あれば、このクリーチャーは
    # 「X」を得る」。engine未模擬の有益キーワード=付与しない=under-model(安全)。
    # ※制限(攻撃できない等)ではなく獲得(得る/持つ)に限定し over-model を避ける
    r"^自分の.{1,40}(?:あれば|なら|以上なら)[、,]?(?:この|その)クリーチャーは[、,]?[「『].{1,24}[」』]を(?:得る|持つ)$",
    # 条件付き/クラス/クロスのキーワード付与(「X」を得る): 有益な能力付与。engine が
    # 「を得」を静的付与扱いしない(または未模擬キーワード)ため省略=under-model(安全)。
    # ブロッカー/SA等の既知キーワードは keyword_grants/プロパティが別途模擬するので二重に
    # ならない(本節は「解析済み」マークのみ)
    r"^自分の[^。]{1,55}(?:あれば|なら|あるなら|を持つ|がいれば)[、,]?.{0,30}[「『][^」』]{1,45}[」』]を得る$",
    r"^自分の[^。]{1,45}は[、,]?.{0,24}[「『][^」』]{1,45}[」』]を得る$",
    r"^クロスした[^。]{1,30}は[「『][^」』]{1,70}[」』]を得る$",
    r"^(?:このクリーチャーは[、,]?)?パワーを[+＋]\d+し[、,][「『][^」』]{1,40}[」』]を得る$",
    # 他クリーチャー/クラスへの能力付与(「X」を与える): 有益=under-model(安全)
    r"^自分の[^。]{1,45}(?:すべて)?に[「『][^」』]{1,55}[」』]を与える$",
    r"^これ(?:を装備した|でクロスした)?クリーチャーは[「『][^」』]{1,55}[」』]を得る$",
    r"^パワーが\d+以上の(?:時|なら)[、,][「『][^」』]{1,40}[」』]を得る$",
    r"^これがNEO進化クリーチャーなら[、,].{0,30}[「『][^」』]{1,40}[」』]を与える$",
    r"^自分の[^。]{1,40}(?:あれば|なら|以上あれば)[、,].{0,24}[「『][^」』]{1,45}[」』]を与える$",
    # 条件付き自己保護(選ばれない/攻撃されない/ブロックされない): 有益=under-model(安全)
    r"^自分の.{1,40}(?:あれば|なら)[、,]?(?:この|その)クリーチャーは[、,]?(?:相手に)?(?:選ばれない|攻撃されない|ブロックされない)$",
    # 自軍クリーチャーの離脱置換(とどまる/別ゾーン): 有益な保護=付与しない=under-model(安全)
    r"^自分の(?:他の)?クリーチャーが[、,]?相手の.{1,30}(?:効果|バトル|効果またはバトル).{0,12}によって(?:バトルゾーンを離れる|破壊される)時[、,].{1,90}$",
    # 相手のクリーチャー着地置換(出る時かわりに墓地/マナ=ソフトロック除去): 有益=under-model
    r"^(?:自分のターン中[、,])?相手のクリーチャーがバトルゾーンに出る時[、,]かわりに(?:墓地|マナゾーン|山札の一番下)に置(?:かれる|く)$",
    # 自分のブレイク時のシールド公開(情報のみ): neutral=under-model(安全)
    r"^このクリーチャーが相手のシールドをブレイクする時[、,]相手はそのシールドを手札に加えるかわりに公開する$",
]

# 各文明
_CIV = "光水火闇自然"
# 「自然」は2文字なので文字クラスではなく交替で一致させる
_CIV_PAT = r"(?:自然|[光水火闇])"


_AURA_KW = ("スピードアタッカー", "ブロッカー", "スレイヤー", "マッハファイター")


def _is_aura_clause(cl: str) -> bool:
    """「自分の(種族)は『X』を得る/与える」の無条件キーワード付与オーラ(=keyword_grantsで模擬済み)。"""
    if "自分の" not in cl or ("得る" not in cl and "与える" not in cl):
        return False
    if any(t in cl for t in ("なら", "あれば", "ターン", "につき", "数だけ", "ごとに", "以上", "以下")):
        return False
    return any(kw in cl for kw in _AURA_KW)


def _is_replacement_clause(cl: str) -> bool:
    """「破壊されるかわりに(マナ/手札/山札の下)」=destroy_replacementで模擬済みの置換効果。"""
    if "かわりに" not in cl or "破壊さ" not in cl:
        return False
    if any(t in cl for t in ("ターン", "なら", "あれば", "次の")):
        return False
    # シールド化/山札置換は destroy_replacement(mana/hand/deck)が拾わないが、置換先保護を
    # 省略=クリーチャーがそのまま死ぬ=under-model(安全)として静的消費する
    return any(z in cl for z in ("マナゾーンに置く", "手札に戻す", "手札に加える", "山札の一番下",
                                  "シールド化", "シールドゾーンに置く", "山札に加え"))


def _is_static(clause: str) -> bool:
    c = clause.strip().rstrip("。").strip()
    if not c:
        return True
    if _is_aura_clause(c) or _is_replacement_clause(c):
        return True
    return any(re.match(p, c) for p in _STATIC_CLAUSE)


# 条件・未模擬要素を示す語。効果節にこれらが含まれたら exact化しない(reject)。
# 「条件付き効果を無条件適用」する過大評価を構造的に防ぐ。
_REJECT_TOKENS = [
    "シンパシー", "ラビリンス", "革命チェンジ", "革命0",
    "一度", "そのターン", "次の", "ターン中", "ターンの間", "ＧＲ", "GR", "超次元",
    "シールドが", "場合", "ごとに", "につき", "だけ", "選んでもよい", "見て", "公開",
    "または", "探索", "マナゾーンから", "山札から", "それより", "大きい",
    "コストを支払", "踏み倒", "山札を見", "から探", "進化", "EXライフ", "封印", "侵略",
    "革命チェンジ", "ニンジャ", "メクレイド", "までの数", "数だけ", "枚以上", "体以上",
    "選び、", "選んで", "バトルする", "バトルさせ",
    "与える", "得る", "になる", "扱う", "代わりに", "かわりに",
    "アンタップしない", "攻撃する", "攻撃できない", "ブロックされない", "出さない",
]


def _scope_for(clause: str) -> tuple[str, str | None] | None:
    """対象の所有者と chooser を判定。曖昧なら None(=reject)。

    戻り (scope, chooser): scope='opponent'/'self', chooser='opponent' or None。
    """
    # 「相手は自身の…」= 相手が自分の盤面から選ぶ(chooser opponent, scope opponent)
    if "相手は自身の" in clause or "相手は自分の" in clause:
        return ("opponent", "opponent")
    has_aite = "相手の" in clause
    has_jibun = "自分の" in clause
    if has_aite and not has_jibun:
        return ("opponent", None)
    if has_jibun and not has_aite:
        return ("self", None)
    # 「このクリーチャー」=効果元自身(=自分側)。相手指定がなければ self。
    if "このクリーチャー" in clause and not has_aite:
        return ("self", None)
    return None  # 曖昧 → reject


def _count_all(clause: str) -> int:
    if "すべて" in clause or "全て" in clause:
        return 99
    m = re.search(r"(\d+)体(?:まで)?", clause)
    if m:
        return int(m.group(1))
    return 1


def _restrictions(clause: str) -> dict[str, Any]:
    r: dict[str, Any] = {}
    m = re.search(r"コスト(\d+)以下", clause)
    if m:
        r["max_cost"] = int(m.group(1))
    m = re.search(r"パワー(\d+)以下", clause)
    if m:
        r["max_power"] = int(m.group(1))
    if "ブロッカー" in clause:
        r["target_filter"] = "blocker"
    if "進化でない" in clause or "進化ではない" in clause:
        r["exclude_evolution"] = True
    return r


# アクション動詞の系統(取りこぼし検出用)。節内に複数系統あれば単一パターンでは不足。
_ACTION_FAMILIES = [
    ("引く", "引き"), ("捨てる", "捨て"), ("破壊",), ("タップする",), ("アンタップ",),
    ("手札に戻",), ("マナゾーンに置く",), ("墓地に置く",), ("シールド化", "シールドゾーンに置く", "シールドを"),
]


def _family_count(cl: str) -> int:
    # 「アンタップする」=動作、「アンタップしている」=対象記述(数えない)。
    s = cl.replace("アンタップする", "\x01").replace("アンタップ", "")
    # 「シールドを手札に戻す/追加する」を own_shield 系として一時マーク
    # 「シールドを破壊」等と区別するため「シールドを」全体を一時置換
    s = re.sub(r"シールドを(\d+つ?(?:まで)?)(手札に戻|追加)", "シールド\x02", s)
    fams = [("引く", "引き"), ("捨て",), ("破壊",), ("タップする",), ("\x01",),
            ("手札に戻",), ("マナゾーンに置く",), ("墓地に置く",),
            ("シールド化", "シールドゾーンに置く", "\x02")]
    return sum(1 for fam in fams if any(w in s for w in fam))


def _split_compound(cl: str) -> list[str]:
    """連用中止「引き、」や接続「その後、」「した後、」で結ばれた複合節を分解する。"""
    s = cl
    s = s.replace("引き、", "引く\x00")
    s = s.replace("、その後、", "\x00").replace("その後、", "\x00")
    s = s.replace("した後に、", "\x00").replace("した後、", "\x00").replace("した後に", "\x00")
    # 連用中止法(動詞連用形+「、」)を終止形に直して分割する。動作の区切りとして安全。
    # 終止形を末尾に補うことで各小節を単独のアクションとして解析できる。
    for renyou, shushi in (
        ("捨て、", "捨てる\x00"), ("置き、", "置く\x00"), ("戻し、", "戻す\x00"),
        ("加え、", "加える\x00"), ("タップし、", "タップする\x00"),
        ("アンタップし、", "アンタップする\x00"), ("破壊し、", "破壊する\x00"),
        ("ブレイクし、", "ブレイクする\x00"),
    ):
        s = s.replace(renyou, shushi)
    return [p.strip("、 ") for p in s.split("\x00") if p.strip("、 ")]


def _parse_action_clause(clause: str) -> list[dict[str, Any]] | None:
    """1つの効果節を action のリストに変換。未知・条件付き・曖昧・取りこぼしなら None。"""
    body = clause.rstrip("。")
    all_acts: list[dict[str, Any]] = []
    safe_skipped = False  # safe-body として消費した節があるか(全節 safe-skip なら [] を返す)
    for part in _split_compound(body):
        # 先頭の条件句(マナ武装/革命/墓地枚数等)を抽出。未知条件キーワードがあれば reject。
        condition, rest, had_cond = _extract_condition(part)
        if condition is None and had_cond:
            return None
        r = _parse_action_clause_raw(rest)
        if r is None:
            # 条件付きの有益効果(超次元/踏み倒し/チューター等の safe-skip 対象)は、条件
            # 成否に関わらず効果を飛ばしても under-model(発動しても得しないだけ)で安全。
            if any(re.match(p, rest.rstrip("。")) for p in _SAFE_BODY_PATTERNS):
                safe_skipped = True
                continue
            return None
        if condition:
            for a in r:
                a["condition"] = condition
        all_acts.extend(r)
    if not all_acts:
        # 全節を safe-skip した場合は「解析成功・アクションなし」(=under-model)として [] を返す
        return [] if safe_skipped else None
    # 節全体のアクション系統数 > 生成アクション数 なら取りこぼし → exact化しない
    if _family_count(body) > len(all_acts):
        return None
    return all_acts


def _extract_condition(cl: str) -> tuple[dict[str, Any] | None, str, bool]:
    """先頭の条件句を抽出。(condition, 残り節, 条件キーワード検出) を返す。

    engine._condition_met が対応する条件のみ厳密に拾う。条件キーワードがあるのに
    既知形に合致しなければ (None, cl, True) を返し、呼び出し側で reject させる。
    """
    # マナ武装N：自分のマナゾーンに<civ>のカードがN枚以上あれば、…
    m = re.search(r"自分のマナゾーンに(自然|[光水火闇])のカードが(\d+)枚以上あれば[、,]?(.+)$", cl)
    if m:
        return ({"kind": "mana_civ_at_least", "civilization": m.group(1), "count": int(m.group(2))}, m.group(3), True)
    m = re.search(r"自分のマナゾーンに多色(?:の)?カードが(\d+)枚以上あれば[、,]?(.+)$", cl)
    if m:
        return ({"kind": "mana_multicolor_at_least", "count": int(m.group(1))}, m.group(2), True)
    # 自分のマナゾーンに<civ>のカードがあれば(枚数省略=1枚以上): engine の mana_civ_at_least で模擬
    m = re.search(r"自分のマナゾーンに(自然|[光水火闇])のカードがあれば[、,]?(.+)$", cl)
    if m:
        return ({"kind": "mana_civ_at_least", "civilization": m.group(1), "count": 1}, m.group(2), True)
    m = re.search(r"自分のマナゾーンにカードが(\d+)枚以上あれば[、,]?(.+)$", cl)
    if m:
        return ({"kind": "mana_at_least", "count": int(m.group(1))}, m.group(2), True)
    # 自分のマナゾーンに<種族等>がN枚以上あれば: engine未知条件=Falseで不発=under-model=安全
    m = re.search(r"自分のマナゾーンに[^。、]{1,16}が(\d+)枚以上あれば[、,]?(.+)$", cl)
    if m:
        return ({"kind": "mana_named_at_least", "count": int(m.group(1))}, m.group(2), True)
    m = re.search(r"自分の墓地に(?:カード|クリーチャー)が(\d+)枚以上あれば[、,]?(.+)$", cl)
    if m:
        return ({"kind": "grave_at_least", "count": int(m.group(1))}, m.group(2), True)
    m = re.search(r"自分のシールドが(\d+)つ?以下(?:なら|であれば)[、,]?(.+)$", cl)
    if m:
        return ({"kind": "shields_at_most", "count": int(m.group(1))}, m.group(2), True)
    m = re.search(r"自分のシールドが(?:1つも|まったく)なければ[、,]?(.+)$", cl)
    if m:
        return ({"kind": "shields_at_most", "count": 0}, m.group(1), True)
    m = re.search(r"自分のシールドが(\d+)つ?以上(?:あれば|なら|であれば)[、,]?(.+)$", cl)
    if m:
        return ({"kind": "shields_at_least", "count": int(m.group(1))}, m.group(2), True)
    m = re.search(r"相手のシールドが(\d+)つ?以下(?:なら|であれば)[、,]?(.+)$", cl)
    if m:
        return ({"kind": "opponent_shields_at_most", "count": int(m.group(1))}, m.group(2), True)
    m = re.search(r"相手のシールドが(\d+)つ?以上(?:あれば|なら|であれば)[、,]?(.+)$", cl)
    if m:
        return ({"kind": "opponent_shields_at_least", "count": int(m.group(1))}, m.group(2), True)
    m = re.search(r"自分の(?:最大)?マナが(\d+)以下(?:なら|であれば)[、,]?(.+)$", cl)
    if m:
        return ({"kind": "mana_at_most", "count": int(m.group(1))}, m.group(2), True)
    m = re.search(r"自分の手札が(\d+)枚以下(?:なら|であれば)[、,]?(.+)$", cl)
    if m:
        return ({"kind": "hand_at_most", "count": int(m.group(1))}, m.group(2), True)
    m = re.search(r"自分の手札が(\d+)枚以上(?:あれば|なら)[、,]?(.+)$", cl)
    if m:
        return ({"kind": "hand_at_least", "count": int(m.group(1))}, m.group(2), True)
    # 自分の山札がN枚以上(なら): engine未知条件=Falseで不発=under-model=安全
    m = re.search(r"自分の山札が(\d+)枚以上(?:あれば|なら|であれば)[、,]?(.+)$", cl)
    if m:
        return ({"kind": "deck_at_least", "count": int(m.group(1))}, m.group(2), True)
    # 自分のマナにすべての文明が揃っていれば: engine未知条件(=Falseで発動しない=under-model=安全)
    m = re.search(r"自分のマナゾーンにすべての文明が揃っていれば[、,]?(.+)$", cl)
    if m:
        return ({"kind": "mana_all_civilizations"}, m.group(1), True)
    # 自分のBZにパワーN以上のクリーチャーがあれば: engine未知条件=under-model=安全
    m = re.search(r"自分の(?:バトルゾーンに)?パワー(\d+)以上のクリーチャーが(?:あれば|いれば)[、,]?(.+)$", cl)
    if m:
        return ({"kind": "self_bz_power_at_least", "min_power": int(m.group(1))}, m.group(2), True)
    # 自分のBZにクリーチャーN体以上いれば: engine未知条件=under-model=安全
    m = re.search(r"自分のバトルゾーンにクリーチャーが(\d+)体以上(?:あれば|いれば)[、,]?(.+)$", cl)
    if m:
        return ({"kind": "self_bz_creature_at_least", "count": int(m.group(1))}, m.group(2), True)
    # 相手の最大マナが自分より多ければ: engine未知条件(=Falseで不発=under-model=安全)。
    # 通常ランプ等の有益効果を後段に持つ
    m = re.search(r"相手の(?:最大)?マナが自分(?:のマナ)?より多ければ[、,]?(.+)$", cl)
    if m:
        return ({"kind": "opponent_mana_greater"}, m.group(1), True)
    # 相手のシールドが自分より多ければ: engine未知条件=Falseで不発=under-model=安全
    m = re.search(r"相手のシールドが自分(?:のシールド)?より多ければ[、,]?(.+)$", cl)
    if m:
        return ({"kind": "opponent_shields_greater"}, m.group(1), True)
    # 自分のシールドの数が相手より多ければ: engine未知条件=Falseで不発=under-model=安全
    m = re.search(r"自分のシールド(?:の数)?が相手(?:より|のシールドより)多ければ[、,]?(.+)$", cl)
    if m:
        return ({"kind": "self_shields_greater"}, m.group(1), True)
    # 自分の<種族/属性>が N体/枚以上あれば: engine未知条件=Falseで不発=under-model=安全。
    # マナ/墓地/シールド/手札は上の専用ハンドラで処理済みなので、ここは主に種族カウント。
    m = re.search(r"自分の([^。、]{1,16})が(\d+)(?:体|枚)以上(?:あれば|なら)[、,]?(.+)$", cl)
    if m and not any(z in m.group(1) for z in ("マナ", "墓地", "シールド", "手札", "山札")):
        return ({"kind": "self_named_count_at_least", "count": int(m.group(2))}, m.group(3), True)
    had = any(w in cl for w in ("あれば", "なら", "マナ武装", "革命"))
    return (None, cl, had)


def _parse_action_clause_raw(clause: str) -> list[dict[str, Any]] | None:
    cl = clause.strip().rstrip("。")
    # 「そうした場合、」は前段アクション実行後の逐次効果。reject前に除去して逐次化。
    cl = cl.replace("そうした場合、", "").replace("そうしたら、", "").replace("そうした場合は、", "")
    # エレメント(=クリーチャー/城/タマシード等の総称)はクリーチャーとして近似する。
    # engine はクリーチャーのみ模擬するため、非クリーチャーのエレメントには作用しない
    # =実際より対象が少ない=under-model(安全)。
    cl = cl.replace("エレメント", "クリーチャー")
    # pre-reject ハンドラのために「してもよい/出す」を正規化(正規化本体は reject 後)
    cl = cl.replace("バトルゾーンに出してもよい", "バトルゾーンに出す")

    # --- 文明指定の全体破壊((civ)以外のクリーチャーをすべて破壊する) ---
    # engine: destroy_creatures_nonciv(keep_civ)。デフォルトは両者(自分/相手指定で限定)。
    m = re.match(r"^(自分の|相手の)?(自然|[光水火闇])以外の(?:クリーチャー|カード|エレメント)をすべて破壊する$", cl)
    if m:
        scope = "both"
        if m.group(1) == "自分の":
            scope = "self"
        elif m.group(1) == "相手の":
            scope = "opponent"
        return [{"op": "destroy_creatures_nonciv", "keep_civ": m.group(2), "scope": scope}]

    # --- パワーN以下の全クリーチャー破壊(スコープ省略=両者) ---
    m = re.match(r"^(自分の|相手の)?パワー(\d+)以下のクリーチャーをすべて破壊する$", cl)
    if m:
        mp = int(m.group(2))
        scopes = ["self"] if m.group(1) == "自分の" else (["opponent"] if m.group(1) == "相手の" else ["self", "opponent"])
        return [{"op": "destroy_creature", "count": 99, "max_power": mp, "scope": s} for s in scopes]
    # --- ブロッカーを持つ全クリーチャー破壊(スコープ省略=両者) ---
    m = re.match(r"^(自分の|相手の)?[「『]?ブロッカー[」』]?を持つクリーチャーをすべて破壊する$", cl)
    if m:
        scopes = ["self"] if m.group(1) == "自分の" else (["opponent"] if m.group(1) == "相手の" else ["self", "opponent"])
        return [{"op": "destroy_creature", "count": 99, "target_filter": "blocker", "scope": s} for s in scopes]
    # --- 最大パワーのクリーチャー破壊(engine の対象選択は最強優先=一致) ---
    # 「すべて」(同値タイ複数)でも1体のみ=under-model(安全)。"大きい"は reject 語のため先に処理。
    m = re.match(r"^(自分の|相手の)?最も(?:パワーが大きい|パワーの大きい)クリーチャー(?:をすべて)?を?破壊する$", cl)
    if m:
        scope = "self" if m.group(1) == "自分の" else "opponent"
        return [{"op": "destroy_creature", "count": 1, "scope": scope}]

    # --- マナゾーン召喚(summon_from_mana) ---
    # コスト/パワー/文明/進化でない の組み合わせフィルタに対応。未知修飾語があれば reject。
    if "マナゾーンから" in cl and "バトルゾーンに出す" in cl and "相手" not in cl:
        act: dict[str, Any] = {"op": "summon_from_mana", "count": 1}
        mana_rest = re.sub(r"^(?:自分の)?マナゾーンから[、,]?", "", cl)
        mana_rest = re.sub(r"[、,]?バトルゾーンに出す$", "", mana_rest)

        if "好きな数" in mana_rest:
            mana_rest = re.sub(r"[、,]?クリーチャーを[、,]?好きな数[、,]?$", "", mana_rest)
            act["count"] = 99
        else:
            # extract count ("クリーチャーN体/枚まで")
            m_cnt = re.search(r"クリーチャーを?(\d+)(?:体|枚)(?:まで)?を?(?:[、,]|$)", mana_rest)
            if m_cnt:
                act["count"] = int(m_cnt.group(1))
                mana_rest = mana_rest[:m_cnt.start()] + mana_rest[m_cnt.end():]
            # strip bare "クリーチャーを?"
            mana_rest = re.sub(r"[、,]?クリーチャーを?[、,]?$", "", mana_rest)

        m_cost = re.search(r"コスト(\d+)以下", mana_rest)
        if m_cost:
            act["max_cost"] = int(m_cost.group(1))
            mana_rest = mana_rest.replace(m_cost.group(0), "")
        m_power = re.search(r"パワー(\d+)以下", mana_rest)
        if m_power:
            act["max_power"] = int(m_power.group(1))
            mana_rest = mana_rest.replace(m_power.group(0), "")
        m_civ = re.search(r"(自然|[光水火闇])の", mana_rest)
        if m_civ:
            act["civilizations"] = [m_civ.group(1)]
            mana_rest = mana_rest.replace(m_civ.group(0), "")
        if "進化でない" in mana_rest or "進化ではない" in mana_rest:
            act["exclude_evolution"] = True
            mana_rest = mana_rest.replace("進化でない", "").replace("進化ではない", "")
        mana_rest = re.sub(r"[、,の を]+", "", mana_rest).strip()
        if mana_rest:
            return None
        return [act]

    # --- マナ→墓地(mana_to_grave): マナゾーンからカードを墓地に置く ---
    # 「ランダムな」= engine は最小コスト選択で近似(under-model=安全)
    if "マナゾーンから" in cl and ("墓地に置く" in cl or "墓地に置き" in cl):
        sc = _scope_for(cl) if ("相手" in cl or "自分" in cl) else ("self", None)
        if sc is None:
            return None
        mm = re.search(r"マナゾーンから(?:ランダムな)?(?:カード|クリーチャー)?(\d+)?枚?を?墓地に置(?:く|き)", cl)
        if not mm:
            return None
        cnt = int(mm.group(1)) if mm.group(1) else 1
        scope = "opponent" if sc[0] == "opponent" else "self"
        return [{"op": "mana_to_grave", "count": cnt, "scope": scope}]

    # --- マナ→手札(mana_to_hand): カード/クリーチャー/呪文をマナゾーンから手札に戻す ---
    # 「戻してもよい」(て形)も含めて検出(正規化前なので te-form は raw で確認)
    if "マナゾーンから" in cl and any(p in cl for p in ("手札に戻す", "手札に戻し", "手札に加える")) and "相手" not in cl:
        if "好きな数" in cl:
            return [{"op": "mana_to_hand", "count": 99}]
        # count の位置は「カード1枚を」「カードを1枚」「カードを1枚まで」の3パターン
        mm = re.search(
            r"マナゾーンから[^。]*?(?:カード|クリーチャー|呪文)"
            r"(?:(\d+)枚?を?|を(\d+)枚(?:まで)?)?"
            r"(?:手札に戻す|手札に戻し|手札に加える)", cl)
        if not mm:
            return None
        cnt_raw = mm.group(1) or mm.group(2)
        cnt = int(cnt_raw) if cnt_raw else 1
        return [{"op": "mana_to_hand", "count": cnt}]

    # --- 自己バウンス(このクリーチャーを手札に戻す) ---
    # 「バトルゾーンから手札に戻す」= subject省略型の自己bounce。ターン終了時効果として多い。
    if cl == "バトルゾーンから手札に戻す" or cl == "このクリーチャーを手札に戻す":
        return [{"op": "bounce_creature", "target": "source"}]

    # --- パワー修整(「そのターン」限定。engineのpower_modifierはターン終了でリセット=一致) ---
    if "パワー" in cl and "クリーチャー" in cl and "アタッカー" not in cl and "得る" not in cl:
        mm = re.search(r"パワー(?:を|は|が)?\s*([+＋\-－‐])\s*(\d+)", cl)
        # 「そのターン」以外の永続/条件は未対応なので、それ以外の条件語があれば後段rejectに委ねる
        if mm and not any(t in cl for t in ("革命", "マナ武装", "あれば", "なら", "ごとに", "につき", "数だけ")):
            sc = _scope_for(cl)
            if sc is None:
                return None
            sign = -1 if mm.group(1) in "-－‐" else 1
            delta = sign * int(mm.group(2))
            act = {"op": "modify_power", "scope": sc[0], "delta": delta, "count": _count_all(cl)}
            return [act]

    # --- 蘇生(墓地からバトルゾーンへ) - reject前に処理(進化でないを含むため) ---
    if "墓地から" in cl and "バトルゾーンに出す" in cl and "相手" not in cl:
        # 文明とコストの順序は両方対応。種族限定(ハンター等)は reject。
        _ZONE_COND = r"(?:(?:(自然|[光水火闇])の)?(?:コスト(\d+)以下の)?(?:進化でない)?|(?:コスト(\d+)以下の)?(?:(自然|[光水火闇])の)?(?:進化でない)?)"
        mm = re.fullmatch(
            r"(?:自分の)?墓地から、?" + _ZONE_COND +
            r"、?(?:クリーチャー|カード)(?:(\d+)(?:枚|体)(?:まで)?)?を?(?:(\d+)(?:枚|体)(?:まで)?)?、?バトルゾーンに出す",
            cl)
        if not mm:
            return None
        max_cost_s = mm.group(2) or mm.group(3)
        cnt_raw = mm.group(5) or mm.group(6)
        act: dict[str, Any] = {"op": "summon_from_grave", "count": int(cnt_raw) if cnt_raw else 1}
        if max_cost_s:
            act["max_cost"] = int(max_cost_s)
        return [act]

    # --- 手札召喚(自分の手札からクリーチャーを出す) ---
    # コスト/文明/ブロッカー/進化でない の組み合わせフィルタに対応。未知修飾語があれば reject。
    if "手札から" in cl and "バトルゾーンに出す" in cl and "相手" not in cl and "墓地" not in cl:
        act: dict[str, Any] = {"op": "summon_from_hand", "count": 1}
        hand_rest = re.sub(r"[、,]?(?:自分の)?手札から[、,]?", "", cl)
        hand_rest = re.sub(r"[、,]?バトルゾーンに出す$", "", hand_rest)
        # extract count ("クリーチャーN体/枚まで")
        m_cnt = re.search(r"クリーチャーを?(?:(\d+)(?:体|枚)(?:まで)?を?)?(?=[、,]|$)", hand_rest)
        if not m_cnt:
            return None
        if m_cnt.group(1):
            act["count"] = int(m_cnt.group(1))
        hand_rest = hand_rest[:m_cnt.start()].rstrip("、, ")
        # extract filters
        m_cost = re.search(r"コスト(\d+)以下", hand_rest)
        if m_cost:
            act["max_cost"] = int(m_cost.group(1))
            hand_rest = hand_rest.replace(m_cost.group(0), "")
        m_civ = re.search(r"(自然|[光水火闇])の", hand_rest)
        if m_civ:
            act["civilizations"] = [m_civ.group(1)]
            hand_rest = hand_rest.replace(m_civ.group(0), "")
        if re.search(r'[「“]?ブロッカー[」”]?を持つ', hand_rest):
            act["target_filter"] = "blocker"
            hand_rest = re.sub(r'[「“]?ブロッカー[」”]?を持つ', "", hand_rest)
        if "進化でない" in hand_rest or "進化ではない" in hand_rest:
            act["exclude_evolution"] = True
            hand_rest = hand_rest.replace("進化でない", "").replace("進化ではない", "")
        hand_rest = re.sub(r"[、,のを ]+", "", hand_rest).strip()
        if hand_rest:
            return None
        return [act]

    # 条件・未模擬要素を含む節は exact化しない(過大評価防止の要)
    # 「進化でない/ではない」はフィルタ修飾語(解析可能)なので reject判定から除外する
    _reject_cl = cl.replace("進化でない", "").replace("進化ではない", "")
    if any(tok in _reject_cl for tok in _REJECT_TOKENS):
        return None

    # 任意形(てもよい)は最適プレイで常に実行=engineの有利効果常時使用と一致。
    # 強制形に正規化して既存パターンに載せる。順序重要: 長い形から先に置換。
    cl = cl.replace("捨ててもよい", "捨てる")
    cl = cl.replace("引いてもよい", "引く")
    cl = cl.replace("加えてもよい", "加える")
    cl = cl.replace("置いてもよい", "置く")
    cl = cl.replace("してもよい", "する")

    # --- 自分ドロー(対象なし) ---
    m = re.search(r"カードを(\d+)枚引く", cl)
    if m and "捨て" not in cl and "相手" not in cl:
        return [{"op": "draw", "count": int(m.group(1))}]
    if "カードを1枚引く" in cl and "捨て" not in cl and "相手" not in cl:
        return [{"op": "draw", "count": 1}]

    # --- ハンデス(相手の手札を捨てさせる) ---
    # engineのdiscard_opponent_handはランダム選択なので「ランダムに捨てさせる」と一致=忠実。
    m = re.search(r"相手は(?:自身の)?手札を(\d+)枚捨てる", cl)
    if m:
        return [{"op": "discard_opponent_hand", "count": int(m.group(1))}]
    if "相手は" in cl and "手札を1枚捨てる" in cl:
        return [{"op": "discard_opponent_hand", "count": 1}]
    # 「相手のランダムな手札を1枚捨てさせる」語順にも対応
    m = re.search(r"相手の(?:ランダムな)?手札を?(?:ランダムに)?(\d+)枚(?:を)?捨てさせる", cl)
    if m:
        return [{"op": "discard_opponent_hand", "count": int(m.group(1))}]
    if "相手の手札をランダムに1枚捨てさせる" in cl or "相手の手札を1枚捨てさせる" in cl:
        return [{"op": "discard_opponent_hand", "count": 1}]
    # ピーピング選択ハンデス(相手手札を見せ→「その中からN枚を捨てさせる」)。engine の
    # ランダム選択は最適選択より弱い=under-model(安全)。
    # 「捨てさせる」(使役)は相手に捨てさせる=ハンデス。「その中から」は直前の相手手札公開を指す。
    m = re.search(r"その中から(\d+)枚を?捨てさせる", cl)
    if m:
        return [{"op": "discard_opponent_hand", "count": int(m.group(1))}]
    # ピーピング指定ハンデス(最も〜のカード/呪文1枚を捨てさせる): engine はランダム=
    # 最適選択より弱い=under-model(安全)
    m = re.search(r"相手の手札から最も.{1,20}(\d+)枚を?捨てさせる", cl)
    if m:
        return [{"op": "discard_opponent_hand", "count": int(m.group(1))}]

    # --- 自己ディスカード(相手指定なし=自分) ---
    m = re.search(r"(?:自分の)?手札を(\d+)枚捨て(?:る)?", cl)
    if m and "選" not in cl and "相手" not in cl:
        return [{"op": "discard_own_hand", "count": int(m.group(1))}]
    # 「自分の手札から(種別)?N枚を捨てる」語順。任意(てもよい)は強制化済み=under-model。
    # engine の discard_own_hand は方策選択なので種別フィルタは無視(=任意の1枚を捨てる近似)。
    m = re.search(r"自分の手札から(?:[^。]{0,12}?)(\d+)枚(?:を)?捨て(?:る)?", cl)
    if m and "相手" not in cl:
        return [{"op": "discard_own_hand", "count": int(m.group(1))}]
    if re.search(r"自分の手札をすべて捨て(?:る)?", cl) and "相手" not in cl:
        return [{"op": "discard_own_hand", "count": 99}]
    if ("相手は手札をすべて捨てる" in cl) or ("相手は自身の手札をすべて捨てる" in cl):
        return [{"op": "discard_opponent_hand", "count": 99}]

    # --- アンタップ ---
    if "アンタップする" in cl:
        # 対象記述なし or 「このクリーチャー」= 効果元自身をアンタップ
        if "クリーチャー" not in cl or ("このクリーチャー" in cl and "相手" not in cl):
            return [{"op": "untap_creature", "target": "source"}]
        sc = _scope_for(cl)
        if sc is None:
            return None
        return [{"op": "untap_creature", "count": _count_all(cl), "scope": sc[0]}]

    # --- 自己リソース(マナ加速/シールド追加/シールド手札/自己ミル): 相手対象でないもののみ ---
    if "相手" not in cl:
        # マナ加速: 山札の上からN枚(目)をマナゾーンに置く / 山札の上からカードをマナゾーンに置く(=1枚)
        m = re.search(r"山札の上から(\d+)枚目?を[、,]?(?:自分の)?マナゾーンに置く", cl)
        if m and "墓地" not in cl:
            return [{"op": "deck_top_to_mana", "count": int(m.group(1))}]
        if re.search(r"山札の上からカードを?(?:1枚)?[、,]?(?:自分の)?マナゾーンに置く", cl) and "墓地" not in cl:
            return [{"op": "deck_top_to_mana", "count": 1}]
        # シールド追加: 山札の上からN枚(目)をシールド化 / シールドゾーンに置く / シールドをN追加
        m = re.search(r"山札の上から(\d+)枚目?を[、,]?(?:自分の)?シールド(?:化|ゾーンに置く)", cl)
        if m:
            return [{"op": "add_shield", "count": int(m.group(1))}]
        m = re.search(r"自分のシールドを(\d+)つ追加", cl)
        if m:
            return [{"op": "add_shield", "count": int(m.group(1))}]
        # 「(更に)もうN枚をシールド化する」= 山札の上をシールド追加(source省略)
        m = re.search(r"(?:更に)?もう(\d+)枚を?シールド化する", cl)
        if m:
            return [{"op": "add_shield", "count": int(m.group(1))}]
        if re.search(r"(?:更に)?もう1枚を?シールド化する", cl):
            return [{"op": "add_shield", "count": 1}]
        # シールド→手札: 自分のシールドをNつ手札に戻す/加える(S・トリガーなし=under-model側で安全)
        # 「シールドを1つ」「シールド1つを」の両語順に対応
        m = re.search(r"自分の(?:ランダムな)?シールド(?:を)?(\d+)つ?(?:を)?(?:まで)?手札に(?:戻す|加える)", cl)
        if m:
            return [{"op": "own_shield_to_hand", "count": int(m.group(1))}]
        if any(p in cl for p in ("自分のシールドをすべて手札に戻す", "自分のシールドをすべて手札に加える",
                                   "自分のシールドを好きな数手札に戻す", "自分のシールドを好きな数手札に加える")):
            return [{"op": "own_shield_to_hand", "count": 99}]
        # シールド→墓地: 自分の(ランダムな)?シールドをN枚墓地に置く(コスト=必ず模擬する)
        m = re.search(r"自分の(?:ランダムな)?シールド(?:を)?(\d+)つ?(?:を)?墓地に置く", cl)
        if m and "相手" not in cl:
            return [{"op": "own_shield_to_grave", "count": int(m.group(1))}]
        # 自己シールドブレイク: 手札に入る近似(S・トリガー無視=under-model)
        m = re.search(r"自分の(?:ランダムな)?シールド(?:を)?(\d+)つ?(?:を)?ブレイクする", cl)
        if m and "相手" not in cl:
            return [{"op": "own_shield_to_hand", "count": int(m.group(1))}]
        # 手札→シールド: 自分の手札N枚をシールド化する
        if "シールド化" in cl and "相手" not in cl:
            m = re.search(r"(?:自分の)?手札(\d+)?枚?をシールド化", cl)
            if m:
                cnt = int(m.group(1)) if m.group(1) else 1
                return [{"op": "hand_to_shield", "count": cnt}]
        # 手札→マナ: 「手札からN枚」「手札N枚」「手札をN枚」いずれも対応
        m = re.search(r"(?:自分の)?手札(?:から|を)?(\d+)枚(?:を)?マナゾーンに置く", cl)
        if m:
            return [{"op": "hand_to_mana", "count": int(m.group(1))}]
        if "手札を好きな数マナゾーンに置く" in cl or "手札を好きな数マナゾーンに置いて" in cl:
            return [{"op": "hand_to_mana", "count": 99}]
        # 自己ミル: 自分の山札の上からN枚(目)を墓地に置く
        m = re.search(r"山札の上から(\d+)枚目?を[、,]?(?:自分の)?墓地に置く", cl)
        if m:
            return [{"op": "deck_top_to_grave", "count": int(m.group(1))}]

    # 相手ミル: 相手の山札の上からN枚を墓地に置く
    m = re.search(r"相手の山札の上から(\d+)枚を[、,]?墓地に置く", cl)
    if m:
        return [{"op": "deck_top_to_grave", "count": int(m.group(1)), "scope": "opponent"}]

    # --- シールドブレイク(相手のシールドを墓地へ) ---
    m = re.search(r"相手のシールドを(\d+)つ(?:、|を)?(?:墓地に置く|ブレイクする)", cl)
    if m:
        return [{"op": "burn_opponent_shield", "count": int(m.group(1))}]
    if "相手のシールド1つを墓地に置く" in cl or "相手のシールドを1つブレイクする" in cl:
        return [{"op": "burn_opponent_shield", "count": 1}]

    # --- 墓地回収/墓地→マナ/手札→マナ(種別フィルタ付き) ---
    def _cardfilter(s: str) -> str | None:
        if "クリーチャー" in s:
            return "creature"
        if "呪文" in s:
            return "spell"
        return None

    if "墓地から" in cl and "手札に戻" in cl and "相手" not in cl:
        m = re.search(r"墓地から(?:.{0,12}?)(\d+)?枚", cl)
        cnt = int(m.group(1)) if (m and m.group(1)) else 1
        act = {"op": "grave_to_hand", "count": cnt}
        cf = _cardfilter(cl)
        if cf:
            act["card_filter"] = cf
        return [act]
    if "墓地から" in cl and "マナゾーンに置く" in cl and "相手" not in cl:
        act = {"op": "grave_to_mana", "count": 1}
        cf = _cardfilter(cl)
        if cf:
            act["card_filter"] = cf
        return [act]
    if "手札から" in cl and "マナゾーンに置く" in cl and "相手" not in cl:
        m = re.search(r"手札から(?:.{0,12}?)(\d+)枚", cl)
        cnt = int(m.group(1)) if m else 1
        return [{"op": "hand_to_mana", "count": cnt}]

    # 以下はクリーチャー対象(戦場)。墓地・ランダム指定は別機構/未模擬なので除外。
    # (engineはクリーチャーを方策で選ぶため、テキストの「ランダムな1体」とは一致しない)
    if "墓地" in cl or "ランダム" in cl:
        return None
    needs_target = ("クリーチャー" in cl)

    # スコープ省略の全体効果(すべて/全て)は両者対象。省略すると自軍分が消えて over-model に
    # なるため、両者(self+opponent)に展開する。「他の」=自身除外は未対応なので除く。
    _is_mass_both = ("すべて" in cl or "全て" in cl) and "他の" not in cl

    # --- 破壊 ---
    if "破壊する" in cl and needs_target:
        sc = _scope_for(cl)
        if sc is None:
            if _is_mass_both:
                r = _restrictions(cl)
                return [{"op": "destroy_creature", "count": 99, "scope": s, **r} for s in ("self", "opponent")]
            # 「他のクリーチャーをすべて破壊する」(スコープ省略)= 両者、自軍は自身除外
            if ("すべて" in cl or "全て" in cl) and "他の" in cl:
                return [
                    {"op": "destroy_creature", "count": 99, "scope": "opponent"},
                    {"op": "destroy_creature", "count": 99, "scope": "self", "exclude_source": True},
                ]
            return None
        scope, chooser = sc
        act = {"op": "destroy_creature", "count": _count_all(cl), "scope": scope}
        act.update(_restrictions(cl))
        if chooser:
            act["chooser"] = chooser
        if "このクリーチャー" in cl and "相手" not in cl:
            act["target"] = "source"  # 効果元自身を破壊
        elif "他の" in cl and scope == "self":
            act["exclude_source"] = True  # 「自分の他の…」=自身を除外
        return [act]

    # --- タップ ---
    if "タップする" in cl and needs_target:
        sc = _scope_for(cl)
        if sc is None:
            if _is_mass_both:
                return [{"op": "tap_creature", "count": 99, "scope": s} for s in ("self", "opponent")]
            return None
        act = {"op": "tap_creature", "count": _count_all(cl), "scope": sc[0]}
        return [act]

    # --- バウンス(手札に戻す) ---
    if "手札に戻" in cl and needs_target:
        sc = _scope_for(cl)
        if sc is None:
            if _is_mass_both:
                r = {k: v for k, v in _restrictions(cl).items() if k != "target_filter"}
                return [{"op": "bounce_creature", "count": 99, "scope": s, **r} for s in ("self", "opponent")]
            return None
        act = {"op": "bounce_creature", "count": _count_all(cl), "scope": sc[0]}
        act.update({k: v for k, v in _restrictions(cl).items() if k != "target_filter"})
        if sc[1]:
            act["chooser"] = sc[1]
        return [act]

    # --- マナ送り(クリーチャーをマナゾーンに置く) ---
    if "マナゾーンに置く" in cl and needs_target:
        sc = _scope_for(cl)
        if sc is None:
            if _is_mass_both:
                r = {k: v for k, v in _restrictions(cl).items() if k != "target_filter"}
                return [{"op": "send_creature_to_mana", "count": 99, "scope": s, **r} for s in ("self", "opponent")]
            return None
        act = {"op": "send_creature_to_mana", "count": _count_all(cl), "scope": sc[0]}
        act.update({k: v for k, v in _restrictions(cl).items() if k != "target_filter"})
        return [act]

    return None


# 効果本体が既知の「under-model=安全な無視可能効果」パターン。
# _parse_action_clause が None を返す前にこれらをチェックしてスキップする。
_SAFE_BODY_PATTERNS = [
    # そのターン限定の追加攻撃能力付与(engine未対応=under-model=安全)
    r"^そのターン[、,](?:(?:この|その)クリーチャーは[、,]?)?(?:アンタップしているクリーチャーを攻撃できる|相手プレイヤーを攻撃できる|プレイヤーを攻撃できる)$",
    r"^(?:この|その)ターン[、,](?:(?:この|その)クリーチャーは[、,]?)?(?:アンタップしているクリーチャーも攻撃できる)$",
    # サイキック・クリーチャー全破壊(超次元=engine未対応=under-model=安全)
    r"^サイキック・クリーチャーをすべて破壊する$",
    r"^自分と相手のサイキック・クリーチャーをすべて破壊する$",
    # バトルさせる: 強制バトル。engine未対応=under-model=安全
    r"^相手のクリーチャー1体を選び[、,]このクリーチャーとバトルさせてもよい$",
    r"^または攻撃する時[、,]相手のクリーチャー1体を選び[、,]このクリーチャーとバトルさせてもよい$",
    # 選択のみ(効果は次文): engine未対応=under-model=安全
    r"^相手のクリーチャーを?\d*体?(?:まで)?を?選ぶ$",
    r"^他のクリーチャー1体を選ぶ$",
    # ターン終了まで攻撃・ブロック不可付与: engine未対応=under-model=安全
    r"^次の(?:自分の)?ターン開始時まで[、,]そのクリーチャーは攻撃もブロックもできない$",
    r"^次の相手のターン開始時まで[、,]そのクリーチャーは攻撃もブロックもできない$",
    r"^次の自分のターン開始時まで[、,]そのクリーチャーは攻撃もブロックもできない$",
    # 残りをシャッフルしてデッキ下に: engine未対応(look_and_take の残りはデッキ底=under-model=安全)
    r"^残りをランダムな順番で山札の一番下に置く$",
    r"^(?:その後[、,])?残りをランダムな順番で山札の一番下に置く$",
    # 山札シャッフル: engine未対応=under-model=安全
    r"^(?:その後[、,])?(?:自分の)?山札をシャッフルする$",
    # 超次元ゾーンからの召喚: engine未対応=under-model=安全
    r"^自分の超次元ゾーンから.{1,80}バトルゾーンに出(?:す|してもよい)$",
    # 墓地/手札からコストを支払わず唱える(任意・有益): engine未対応=under-model=安全
    r"^自分の(?:墓地|手札)から[、,]?.{1,80}コストを支払わずに唱えてもよい$",
    # 墓地からの任意召喚(種族/動的フィルタで通常パーサが拾えない): engine未対応=under-model=安全
    r"^自分の墓地から[、,]?.{1,80}バトルゾーンに出(?:す|してもよい)$",
    # 手札からの踏み倒し召喚(種族フィルタ): engine未対応=under-model=安全
    r"^自分の手札から[、,]?.{1,80}バトルゾーンに出(?:す|してもよい)$",
    # マナゾーンからの踏み倒し召喚(動的コストフィルタ等): engine未対応=under-model=安全
    r"^自分のマナゾーンから[、,]?.{1,80}バトルゾーンに出(?:す|してもよい)$",
    # 相手クリーチャー/エレメントのシールド化・封印化(=非標準の除去): engine未対応=
    # 除去されない=under-model=安全
    r"^相手の.{0,30}(?:クリーチャー|エレメント)\d*[体つ]?を?シールド化する$",
    r"^相手の(?:クリーチャー|エレメント)\d*[体つ]?を?表向きにしてシールド\d*つ?の上に置く$",
    # 探索/超探索(墓地/マナ/山札からの種別タッチ・サーチ)=有益チューター。engine未対応=
    # under-model=安全。行き先は手札/バトルゾーン/唱える/公開いずれも有益
    r"^自分の(?:墓地|マナゾーン|山札)から.{0,40}(?:超)?探索し.{0,40}(?:手札に(?:戻す|加える|戻し|加え)|バトルゾーンに出(?:す|してもよい)|マナゾーンに置(?:く|いてもよい)|唱える|唱えてもよい|公開(?:する|してもよい))(?:てもよい)?$",
    # 一時キーワード付与(そのターン、自分のクリーチャーに「X」を得る/与える): 有益=under-model
    r"^そのターン[、,]自分の(?:他の)?クリーチャー\d*体?に[「『].{1,30}[」』]を(?:得る|与える)$",
    r"^(?:この|その)ターン[、,][「『][^」』]{1,30}[」』]を得る$",
    # 一時的キーワード付与(対象/クラス問わず): 有益=under-model(安全)
    r"^(?:この|その)ターン[、,](?:自分の|その)(?:他の)?[^。]{0,24}(?:は|に)[「『][^」』]{1,50}[」』]を(?:得る|与える)$",
    r"^次の自分のターン開始時まで[、,]そのクリーチャーに[「『][^」』]{1,40}[」』]を与える$",
    # 一時パワー倍化(自軍/自身): 有益=under-model(安全)
    r"^(?:この|その)ターン[、,]自分の[^。]{1,40}のパワーを\d+倍に?(?:する|し[、,][^。]{1,50})$",
    r"^(?:この|その)ターン[、,](?:この|その)クリーチャーのパワーを\d+倍に?する$",
    # 相手クリーチャーのパワー固定値化(デバフ): 有益=under-model(安全)
    r"^(?:自分のターン中[、,])?相手の[^。]{1,40}のパワーは\d+になる$",
    r"^それが[^。]{1,30}なら[、,](?:この|その)ターン[、,][^。]{0,24}[「『][^」』]{1,40}[」』]を得る$",
    r"^そのクリーチャーがバトルゾーンに出た時[、,](?:この|その)ターン[、,][^。]{0,24}[「『][^」』]{1,40}[」』]を(?:得る|与える)$",
    # 自己キーワード獲得(このクリーチャーは「X」を得る/持つ): engine が「を得」を付与扱い
    # せず未模擬のため、省略しても under-model(有益キーワード欠落)=安全
    r"^(?:この|その)クリーチャーは[、,]?[「『].{1,24}[」』]を(?:得る|持つ)$",
    # 一時パワー付与+おまけ(パワー+Nし、…): 有益=under-model
    r"^パワーを[+＋]\d+し[、,].{1,50}$",
    # 相手クリーチャーの山札送り(バウンス除去): 有益除去=under-model
    r"^相手の.{0,20}クリーチャー\d*体?を(?:相手の)?山札に(?:加えてシャッフルする|戻す)$",
    # 公開/表向きカードの配置(look解決): 中立=under-model
    r"^(?:その後[、,])?表向きにしたカードを.{1,30}(?:置く|加える|戻す)$",
    # ガチンコ・ジャッジ: 山札トップのコスト比較。engine未対応=勝てない=under-model=安全
    r"^相手とガチンコ・ジャッジする$",
    r"^自分が勝(?:ったら|てば)[、,].*$",
    # 公開カード参照の条件付き効果(LATで引いたカードの文明等を条件にする): engine は公開
    # カードを参照できない=条件不成立=under-model=安全
    r"^(?:このようにして)?公開したカードが.{1,50}であれば[、,].*$",
    r"^(?:この|その)カードが.{1,40}なら[、,]相手の.{1,80}$",
    # 公開/表向きカードの山札置き直し(look解決の一部): 中立=under-model
    r"^(?:自分の)?山札をシャッフルし[、,]?公開したカードを.{1,20}(?:置く|戻す|加える)$",
    r"^公開したカードを.{1,25}(?:置く|戻す|加える)$",
    # 公開カードの種別条件で相手対象/自軍ランプ等の有益効果(それが…なら、相手の…/自分の山札…):
    # engine は公開カードを参照不可=条件不成立=under-model=安全。対象が相手/自分の山札に
    # 限定して self-restriction の取りこぼしを避ける
    r"^それが.{1,40}(?:なら|であれば)[、,]相手の.{1,80}$",
    r"^それが.{1,40}(?:なら|であれば)[、,]自分の山札.{1,60}$",
    r"^そのカードが.{1,30}(?:なら|であれば)[、,](?:相手の|自分の山札).{1,60}$",
    # 一時的キーワード付与(次のターンまで「X」を得る): 有益付与=skip=under-model=安全
    r"^次の(?:自分の|相手の)?ターン開始時まで[、,]そのクリーチャーは[「『].{1,20}[」』]を得る$",
    # NOTE: 「パワー+N され、相手プレイヤーを攻撃できない」型は攻撃制限の省略が自軍
    # クリーチャーでは over-model(本来不可の本体攻撃が可能になる)になり得るため追加しない。
    # 相手の呪文/攻撃ロック(次ターンまで): 有益=skip=under-model=安全
    r"^次の(?:自分の)?ターン開始時まで[、,]相手は(?:自分の)?呪文を唱えられない$",
    r"^次の(?:自分の)?ターン開始時まで[、,]相手の.{1,40}は(?:.{0,10})?攻撃できない$",
    # else分岐(そうしなかった場合、有益効果): 主効果を強制実行するため else は発生しない。
    # ※ else が自己ペナルティ(破壊等)の場合は省略すると over-model になるため、明確に
    # 有益な効果(引く/マナ/シールド追加)に限定する
    r"^そうしなかった場合[、,](?:カードを\d+枚引く|自分の山札の上から\d+枚を?マナゾーンに置く|自分のシールドを\d+つ追加する)$",
    # 相手の墓地リセット(山札に戻してシャッフル/山札の下): 墓地利用妨害=有益=under-model=安全
    r"^相手は[、,]?自身の墓地(?:に)?ある?カードをすべて山札に加えてシャッフルする$",
    r"^相手の墓地にあるカードをすべて[、,]?.{0,20}山札の(?:一番下|下)に置く$",
    # 任意枚数の自己ディスカード(好きな枚数捨ててもよい): 0枚も選択可=捨てない=
    # under-model(安全)。墓地肥やし用途を取りこぼすが過小評価側
    r"^自分の手札を好きな枚数捨ててもよい$",
    # ゲーム外(超GR/サイドボード等)からの獲得: engine未対応=得られない=under-model(安全)
    r"^ゲーム外から.{1,80}(?:手札に加える|バトルゾーンに出す|手札に加えてもよい|バトルゾーンに出してもよい)$",
    # シールドの確認(情報のみ、ゾーン移動なし): engine 状態に影響なし=neutral=安全
    r"^(?:自分|相手|いずれかのプレイヤー)の?シールド\d*つ?を見る$",
    # 任意のシールド→マナ(好きな数=0可): 任意=under-model(安全)
    r"^自分のシールドを好きな数[、,]?マナゾーンに置く$",
    # 動的シールドブレイク(相手のシールドがN枚になるように): engine の固定数では再現不能=
    # 省略=ブレイクしない=under-model(安全)
    r"^相手のシールドが\d+つ?になるように[、,]?.{0,20}(?:シールド|ランダムなシールド)を?ブレイクする$",
    # 相手手札の公開/見せる(情報のみ、ゾーン移動なし): engine 状態に影響なし=neutral=安全
    r"^相手の手札から最も.{1,60}公開させる$",
    r"^相手は自身の手札を(?:すべて)?見せる$",
    # 動的ランプ(マナの枚数に比例して山札からマナ加速): engine の固定枚数では再現不能の
    # ため省略=ランプしない=under-model(安全)
    r"^自分のマナゾーンにある.{1,30}と同じ枚数のカードを[、,]自分の山札の上からマナゾーンに置く$",
    # 動的ドロー(文明数/枚数/体数に比例): engine の固定枚数では再現不能=省略=引かない=under-model
    r"^自分のマナゾーンにある(?:文明1つ|.{1,16}の数)につき[、,]?カードを\d+枚引く$",
    r"^自分のマナゾーンにある.{1,20}の数だけ[、,]?カードを引く$",
    r"^自分の.{1,30}\d+体につき[、,]?カードを\d+枚引く$",
    r"^自分の.{1,30}の数だけ[、,]?カードを引く$",
    # クロスギア/P'S封印の墓地送り(engine未対応の要素): under-model(安全)
    r"^相手のクロスギア\d*枚?を?墓地に置く$",
    r"^自分のP'S封印\d*つ?を?墓地に置く$",
    # シールドの上にカードを置く(スーパーシールド): engine未対応の保護=under-model(安全)
    r"^自分の山札の上から\d+枚目を[、,]?自分のシールド\d*つ?の上に(?:表向きにして)?置く$",
    # 自分の墓地リセット(山札に戻す/デッキアウト回避): engine未対応=墓地残存=under-model(安全)
    r"^自分の墓地にあるカードをすべて山札に(?:加え|戻し)[、,]?シャッフルする$",
    # 数に比例するタップ(クリーチャー数だけ): engine 固定数では再現不能=省略=under-model(安全)
    r"^自分の.{1,20}の数だけ[、,]?(?:ランダムな)?相手の(?:アンタップしている)?クリーチャーを?タップする$",
    # 次の能力をN回行う(反復修飾): 省略すると次能力は1回=under-model(安全)
    r"^次の能力を\d+回行う$",
    # 合計値制約の動的複数破壊(パワー/コストの合計がN以下になるように好きな数): engine の
    # 予算選択は未対応=省略=破壊しない=under-model(安全)
    r"^相手のクリーチャーを[、,]?(?:パワー|コスト)の合計が\d+以下になるように好きな数選び[、,]破壊する$",
    # 複数キーワードの一時付与(「A」と「B」と…を与える): 有益=under-model(安全)
    r"^(?:この|その)ターン[、,]自分の[^。]{1,30}(?:すべて)?に[、,]?[「『][^。]{1,90}を(?:得る|与える)$",
    # 任意の手札シャッフル戻し(0枚も選べる): 任意=捨てない選択可=under-model(安全)
    r"^自分の手札をすべて[、,]?ランダムな順番で自分の山札の一番下に置いてもよい$",
    # 敗北回避/勝利阻止(サバイバルロック): engine未対応の保護=付与しない=under-model(安全)
    r"^(?:次の自分のターン開始時まで[、,])?自分はゲームに負けず[、,]相手はゲームに勝てない$",
    r"^(?:次の自分のターン開始時まで[、,])?自分はゲームに負けない$",
    r"^このターン[、,]自分はゲームに負けない$",
    # 相手の「カード」除去(クリーチャー以外の要素も含む総称): engine はクリーチャーのみ
    # 模擬。除去を省略しても engine がより少なく除去する=under-model(安全)。スキップは
    # 常に過小評価側で over-model にならない
    r"^相手の(?:.{0,24})?カードを(?:すべて|好きな数|\d+[体枚つ])?(?:まで)?(?:手札に(?:戻す|加える)|破壊する|マナゾーンに置く|タップする)$",
    # P'S封印(相手クリーチャーへの封印=ソフトロック除去): engine未対応=付けない=
    # under-model(安全)
    r"^.{0,40}相手はそれにP'S封印を\d+つ付ける$",
    r"^相手の.{0,30}クリーチャー.{0,10}にP'S封印を\d+つ付ける$",
    # 手札枚数等に比例する相手クリーチャーのパワー減少(動的デバフ): 相手弱体化=有益=
    # engine の固定値 modify_power では再現不能のため省略=under-model(安全)
    r"^このターン[、,]相手の(?:すべての)?クリーチャー\d*体?の?パワーを[、,]?.{1,30}につき[-－‐]\d+する$",
    # 一時/次回召喚のコスト軽減(有益): engine未対応=より多く払う=under-model(安全)
    r"^このターン[、,]次に召喚する自分の.{1,30}の召喚コストを\d+少なくする$",
    r"^このターン[、,]自分の.{1,30}を(?:召喚|唱える)コストを\d+少なくする$",
    # 数字/文明宣言(ラッキーナンバー等): 宣言自体は無効果。engine は宣言値を扱えないため
    # 後続の数値依存効果(チューター/相手妨害)も発動しない=under-model=安全
    r"^数字を\d+つ選ぶ$",
    r"^(?:自然|[光水火闇])以外の文明を\d+つ選ぶ$",
    # 宣言数値に依存する相手対象効果(バウンス/ロック等): 有益=under-model=安全
    r"^その数字と同じコストを持つ相手の.{1,50}$",
    r"^次の(?:自分の)?ターン開始時まで[、,]相手はその数字と同じコストを持つ.{1,40}を?(?:実行|召喚|唱え)(?:できない|られない)$",
]


# 自分の山札を見る/表向き/公開する起点文(枚数指定の有無・「上から」省略の有無に対応)。
_LOOK_OWN_DECK_RE = re.compile(
    r"^(?:自分の)?山札(?:を(?:シャッフルし、?)?)?(?:の?上)?から\d*枚?(?:目)?を?(?:見る|表向きにする|公開する)"
)
# look-resolution の継続文に現れる、見たカードの行き先キーワード。
_LOOK_RESOLUTION_KEYWORDS = (
    "バトルゾーンに出", "山札の一番下", "山札の一番上", "山札の下", "山札の上",
    "シールド化", "シールドの上", "シールド1つ", "手札に加え", "手札に戻",
    "マナゾーンに置", "墓地に置", "公開", "タップしてバトルゾーン",
)


def _is_look_resolution_sent(s: str) -> bool:
    """「自分の山札を見た後の解決文」かどうか(=engine未対応で under-model 安全に飛ばせる)。

    見たカードの選別・配置(出す/手札/マナ/墓地/シールド/山札へ戻す)や、それに付随する
    注記・静的・安全本体を解決文として認める。これらは engine が何もしない=過小評価=安全。
    """
    c = s.strip().rstrip("。")
    if not c:
        return True
    if _is_static(c) or any(re.match(p, c) for p in _SAFE_BODY_PATTERNS):
        return True
    if _LOOK_OWN_DECK_RE.match(c):
        return True
    if c.startswith(("その", "それ", "残り", "そうした", "それら", "この")):
        if any(k in c for k in _LOOK_RESOLUTION_KEYWORDS):
            return True
    if any(k in c for k in _LOOK_RESOLUTION_KEYWORDS) and "相手" not in c:
        return True
    return False


def _detect_trigger(clause: str) -> tuple[str | None, str]:
    """節の先頭からトリガーを判定し (trigger, 本体) を返す。

    トリガー前置詞がなければ (None, clause)。相手起点の時制は曖昧なので拾わない。
    """
    cl = clause
    m = re.match(r"^(?:このクリーチャーが)?(?:バトルゾーンに)?出た時[、,]?(.+)$", cl)
    if m:
        return ("on_play", m.group(1))
    # 「このクリーチャー、または自分の他の<…>がバトルゾーンに出た時」= 自身ETB+他者ETB。
    # 他者ETBは engine 未発火だが、自身の on_play だけ拾えば発火回数は実際の部分集合=
    # under-model(安全)。
    m = re.match(r"^このクリーチャー[、,]?または自分の(?:他の)?.{1,40}がバトルゾーンに出た時[、,]?(.+)$", cl)
    if m:
        return ("on_play", m.group(1))
    # 「このクリーチャーがどこからでも(自分の)墓地に置かれた時」= 墓地行き全般。engine の
    # on_destroyed(バトルゾーンでの破壊)はその部分集合=under-model(安全)。
    m = re.match(r"^このクリーチャーが(?:どこからでも)?(?:自分の)?墓地に置かれた時[、,]?(.+)$", cl)
    if m and "相手" not in cl[:6]:
        return ("on_destroyed", m.group(1))
    m = re.match(r"^(?:このクリーチャーが)?攻撃する時[、,]?(.+)$", cl)
    if m and "相手" not in cl[:6]:
        return ("on_attack", m.group(1))
    m = re.match(r"^(?:このクリーチャーが)?(?:破壊された時|バトルゾーンを離れた時)[、,]?(.+)$", cl)
    if m and "相手" not in cl[:8]:
        return ("on_destroyed", m.group(1))
    # 「自分のクリーチャーが…時」(「他の」なし)= 自身を含む全味方イベント。自身の on_play/
    # on_destroyed だけ拾えば発火は実際の部分集合=under-model(安全)。「他の」版は自身を
    # 除外するため対象外(自然に不一致)。
    m = re.match(r"^自分のクリーチャーが(?:バトルゾーンに)?出た時[、,]?(.+)$", cl)
    if m:
        return ("on_play", m.group(1))
    m = re.match(r"^自分のクリーチャーが(?:破壊された時|バトルゾーンを離れた時)[、,]?(.+)$", cl)
    if m:
        return ("on_destroyed", m.group(1))
    m = re.match(r"^自分のクリーチャーが攻撃する時[、,]?(.+)$", cl)
    if m:
        return ("on_attack", m.group(1))
    # 進化召喚誘発(このクリーチャーを…の上に置いた時)= 進化クリーチャーの着地。engine は
    # 進化を召喚(on_play)で模擬するため on_play に対応づける(進化体は常に進化着地=過大発火なし)。
    m = re.match(r"^このクリーチャーを進化でないクリーチャーの上に置いた時[、,]?(.+)$", cl)
    if m:
        return ("on_play", m.group(1))
    m = re.match(r"^自分が呪文を唱えた時[、,]?(.+)$", cl)
    if m:
        return ("on_spell_cast", m.group(1))
    m = re.match(r"^自分のターン(?:の)?(?:はじめ|始め|開始時)に?[、,]?(.+)$", cl)
    if m:
        return ("on_turn_start", m.group(1))
    m = re.match(r"^自分のターン(?:の)?終(?:わり|了時)に?[、,]?(.+)$", cl)
    if m:
        return ("on_turn_end", m.group(1))
    m = re.match(r"^(?:このクリーチャーが)?バトルに勝った時[、,]?(.+)$", cl)
    if m:
        return ("on_win", m.group(1))
    m = re.match(r"^(?:この)?攻撃の終わりに[、,]?(.+)$", cl)
    if m:
        return ("on_attack_end", m.group(1))
    return (None, cl)


_LAT_RE = re.compile(
    r"^(?:(?:バトルゾーンに出た時|攻撃する時|バトルに勝った時|自分のターン(?:の)?(?:はじめ|始め)に?)"
    r"[、,])?"
    r"(?:自分の)?山札の上から(\d+)枚(?:目)?を(?:見る|見て|表向きにする|公開する)[。、]?"
    r"その中から(.*?)(?:を)?(すべて|好きな数|\d+)?枚?(?:まで)?(?:を)?(?:自分の)?手札に(?:加え|加える)(?:る|てもよい)?(?:。|、)?"
    r"(?:(?:その後[、,]?)?(?:残り|それ以外)を?(.*?)(?:に|へ)[^。]*(?:置く|戻す))?。?$"
)

# アクション節内での look_and_take 複文パターン(「見る。その中から...加える。残りを...置く」)
_LAT_MULTI_RE = re.compile(
    r"^(?:自分の)?山札の上から(\d+)枚(?:目)?を(?:見る|見て|表向きにする|公開する)$"
)
_LAT_TAKE_RE = re.compile(
    r"^その中から(.*?)(?:を)?(すべて|好きな数|\d+)?枚?(?:まで)?(?:を)?(?:自分の)?手札に(?:加え|加える)(?:る|てもよい)?"
    r"(?:[、,](?:その後[、,]?)?(?:残り|それ以外)を?[^。]*置く)?$"
)
_LAT_REST_RE = re.compile(
    r"^(?:その後[、,]?)?(?:残り|それ以外)を?(.*?)(?:に|へ)?[^。]*置く$"
)


def _try_look_and_take(t: str, is_spell: bool, s_trigger: bool) -> list[dict[str, Any]] | None:
    """純粋な「山札の上からN枚を見て選ぶ」カードを look_and_take に変換。"""
    # 正規化: マーカー除去・S・トリガー/静的節を除去して残りを連結
    norm = re.sub(r"[■◇]", "", t)
    kept = []
    for cl in re.split(r"\n", norm):
        cl = cl.strip()
        if not cl or cl in ("S・トリガー", "シールド・トリガー") or _is_static(cl):
            continue
        kept.append(cl)
    joined = "".join(kept)
    # 「公開してから」等は描写なので除去(枚数捕捉を保つ)
    joined = joined.replace("を公開してから", "を").replace("公開してから", "").replace("を公開し、", "を")
    m = _LAT_RE.match(joined)
    if not m:
        return None
    look = int(m.group(1))
    filt = m.group(2) or ""
    take_raw = m.group(3)
    if take_raw in ("すべて", "好きな数"):
        take = 99
    elif take_raw:
        take = int(take_raw)
    else:
        take = 1
    rest = m.group(4) or ""
    # フィルタ末尾の「N枚」は枚数指定でありフィルタではないので抽出する
    # 例: "1枚" → filt="", take=1 / "ドラゴン1枚" → filt="ドラゴン", take=1
    _cnt_in_filt = re.search(r'(\d+)枚?$', filt)
    if _cnt_in_filt:
        take = int(_cnt_in_filt.group(1))
        filt = filt[:_cnt_in_filt.start()].strip("、,の を")
    # 認識できない絞り込み(種族/名前/コスト以上/探索等)は取りこぼし防止のため reject
    if any(tok in filt for tok in ("探索", "見", "または", "ランダム", "以上", "名前に")):
        return None
    if "コスト" in filt and "以下" not in filt:
        return None
    recognized = ("クリーチャー" in filt or "呪文" in filt or "カード" in filt
                  or any(cv in filt for cv in _CIV))
    if filt.strip() and not recognized:
        return None
    act: dict[str, Any] = {"op": "look_and_take", "look": look, "take": take}
    if "クリーチャー" in filt:
        act["card_filter"] = "creature"
    elif "呪文" in filt:
        act["card_filter"] = "spell"
    mc = re.search(r"コスト(\d+)以下", filt)
    if mc:
        act["max_cost"] = int(mc.group(1))
    mciv = re.search(r"(自然|[光水火闇])(?:の|文明)", filt)
    if mciv:
        act["civilization"] = mciv.group(1)
    if "墓地" in rest:
        act["rest_zone"] = "grave"
    elif "マナ" in rest:
        act["rest_zone"] = "mana"
    elif "一番上" in rest or "山札に" in rest:
        act["rest_zone"] = "deck_top"
    else:
        act["rest_zone"] = "deck_bottom"
    trig = "on_cast" if is_spell else "on_play"
    abilities = [{"trigger": trig, "actions": [act]}]
    if s_trigger:
        abilities.append({"trigger": "s_trigger", "actions": [dict(act)]})
    return abilities


_MODAL_HEADER_RE = re.compile(
    r"次の(?:うち)?(?:から)?(?:いずれか(?:ひとつ|1つ|2つ|つ)?|\d+つ)を選(?:ぶ|んでもよい)"
)


def _parse_modal_option(body: str) -> list[dict[str, Any]] | None:
    """モーダル選択肢1つ(複数文可)を actions に変換。未知ならNone、全静的なら空リスト。"""
    acts: list[dict[str, Any]] = []
    for sent in body.split("。"):
        sent = sent.strip()
        if not sent or _is_static(sent):
            continue
        if any(re.match(p, sent.rstrip("。")) for p in _SAFE_BODY_PATTERNS):
            continue
        r = _parse_action_clause(sent)
        if r is None:
            return None
        acts.extend(r)
    return acts


def _try_modal(t: str, is_spell: bool, s_trigger: bool) -> list[dict[str, Any]] | None:
    """「次のうちいずれかひとつを選ぶ」型の純粋モーダルカードを modal_choice に変換。

    全選択肢(▶)が既知アクションに解析できる場合のみ成功。モーダル以外の本体が
    静的キーワードだけで構成される純粋モーダルカードを対象とする。
    """
    if not _MODAL_HEADER_RE.search(t):
        return None
    # ▶選択肢の本体を抽出
    raw_options = re.findall(r"▶([^▶\n]+)", t)
    if len(raw_options) < 2:
        return None
    # ▶部分を除去した残りを行に分割し、トリガー付きヘッダ行を探す
    remainder = re.sub(r"▶[^▶\n]+", "", t)
    lines: list[str] = []
    for line in re.split(r"[\n]", remainder):
        for part in re.split(r"[■◇]", line):
            p = part.strip()
            if p:
                lines.append(p)
    header_line = None
    for ln in lines:
        if _MODAL_HEADER_RE.search(ln):
            header_line = ln
            continue
        if ln in ("S・トリガー", "シールド・トリガー") or _is_static(ln):
            continue
        # ヘッダ・静的・S・トリガー以外の本体があれば純粋モーダルでない → 諦める
        return None
    if header_line is None:
        return None
    # ヘッダのトリガーを判定
    head = re.sub(r"(?:そうした場合[、,])?" + _MODAL_HEADER_RE.pattern + r"。?$", "", header_line).strip("、, ")
    if head:
        trig, _ = _detect_trigger(header_line)
        trigger = trig
    else:
        trigger = None
    if trigger is None:
        if is_spell:
            trigger = "on_cast"
        else:
            return None
    # 各選択肢を解析
    options: list[list[dict[str, Any]]] = []
    for opt in raw_options:
        acts = _parse_modal_option(opt.strip().rstrip("。"))
        if acts is None:
            return None
        options.append(acts)
    modal_act = {"op": "modal_choice", "options": options}
    abilities = [{"trigger": trigger, "actions": [modal_act]}]
    main_trigger = "on_cast" if is_spell else "on_play"
    if s_trigger and trigger == main_trigger:
        abilities.append({"trigger": "s_trigger", "actions": [dict(modal_act)]})
    return abilities


def parse_card(text: str, card_type: str) -> list[dict[str, Any]] | None:
    """カード全文を exact abilities に変換。全節カバーできなければ None。

    戻り値: abilities リスト(空リスト=静的のみで忠実) または None(exact化不可)。
    """
    if text is None:
        return []
    t = text.strip()
    if not t:
        return []  # バニラ=空abilityが忠実

    is_spell = "呪文" in (card_type or "")
    # S・トリガー: 「使えない」文脈(シールド手戻し注記)を除外、スーパーST除外
    s_trigger = bool(
        re.search(r"[◇◆]S・トリガー|^S・トリガー$|シールド・トリガー", t, re.MULTILINE)
    ) and "スーパー" not in t

    lat = _try_look_and_take(t, is_spell, s_trigger)
    if lat is not None:
        return lat

    modal = _try_modal(t, is_spell, s_trigger)
    if modal is not None:
        return modal

    # ■◇と改行でアビリティ単位に分割(各アビリティ内の。区切りはトリガーを共有する継続節)
    ability_chunks: list[str] = []
    for line in re.split(r"[\n]", t):
        for part in re.split(r"[■◇]", line):
            p = part.strip()
            if p:
                ability_chunks.append(p)

    by_trigger: dict[str, list[dict[str, Any]]] = {}
    prev_chunk_trigger: str | None = None
    # ツインパクト: 【LINE】以降の節はスペル側(呪文)扱い→on_cast をデフォルトトリガーに使う
    after_line = False
    # 別チャンクに分かれた look-resolution(「見る」の解決が次の■にある)を飛ばすための状態。
    look_skip_active = False

    for chunk in ability_chunks:
        # 【LINE】はツインパクトのクリーチャー/スペル境界マーカー
        if re.fullmatch(r"【LINE】", chunk):
            after_line = True
            continue
        if chunk in ("S・トリガー", "シールド・トリガー") or _is_static(chunk):
            continue
        # 直前チャンクが「自分の山札を見る」だけだった場合、その解決(その中から…/残り…)が
        # 別の■チャンクに続くことがある。純粋な解決チャンクなら under-model で飛ばす。
        if look_skip_active:
            res_sents = [s.strip() for s in chunk.split("。") if s.strip()]
            if res_sents and all(_is_look_resolution_sent(s) for s in res_sents):
                continue
            look_skip_active = False
        # 「その後、」で始まるチャンクは直前チャンクのトリガーを引き継ぐ
        inherited_trigger: str | None = None
        if chunk.startswith("その後、") or chunk.startswith("その後,"):
            inherited_trigger = prev_chunk_trigger
            chunk = chunk[4:].lstrip("、,")
        sentences = [s.strip() for s in chunk.split("。") if s.strip()]
        chunk_trigger: str | None = inherited_trigger
        skip_until: int = -1  # LAT複文処理でスキップする文インデックス上限
        for si, sent in enumerate(sentences):
            if si <= skip_until:
                continue
            # キーワードラベル(条件が後段に明記される型)を除去
            sent = re.sub(r"^(?:マスター)?G・G・G[：:]", "", sent).strip()
            # マナ武装 N：は条件が本文中に記載されるので接頭語のみ除去
            sent = re.sub(r"^(?:多色)?マナ武装\s*\d+[：:]", "", sent).strip()
            # 革命N：は革命シールド条件の接頭語。本文中の「シールドが...以下なら」で処理
            sent = re.sub(r"^革命[0-9][：:]", "", sent).strip()
            # 【SST】等のマーカー行はスーパーSトリガー等の条件付き追加効果。条件を満たした時
            # のみ発動するため、無条件適用は過大評価。マーカー以降のこのチャンク全体を無視
            # (=発動しない=under-model=安全)。【LINE】はチャンク単位で別途処理済み。
            if re.match(r"^【[^】]+】", sent):
                break
            if _is_static(sent):
                continue
            if is_spell or after_line:
                # 呪文側またはツインパクトスペル側: on_cast をデフォルトに
                trig_d, body_d = _detect_trigger(sent)
                if trig_d is not None:
                    trigger, body = trig_d, body_d
                else:
                    trigger, body = "on_cast", sent
            else:
                trigger, body = _detect_trigger(sent)
                if trigger is None:
                    if chunk_trigger is not None:
                        trigger, body = chunk_trigger, sent  # 継続節はトリガー継承
                    else:
                        return None  # トリガー不明 → exact化不可
            chunk_trigger = trigger
            # デュアルトリガー(「Aする時、またはBする時、効果」)の検出。本体を両トリガーに登録。
            extra_triggers: list[str] = []
            mdt = re.match(r"^または(.+?[時に])[、,](.+)$", body)
            if mdt:
                t2, _b2 = _detect_trigger(mdt.group(1) + "、_")
                if t2 is not None:
                    extra_triggers.append(t2)
                    body = mdt.group(2)
            # 文頭の逐次マーカー「その後、」を除去(トリガーは継承済み)。安全節/通常解析の
            # マッチを揃える。
            body = re.sub(r"^その後[、,]", "", body).strip()
            # LAT複文検出: 「山札の上からN枚を見る/表向きにする」の後続文を結合して look_and_take に変換
            if _LAT_MULTI_RE.match(body):
                lat_sents = [body]
                j = si + 1
                while j < len(sentences):
                    ns = sentences[j].strip()
                    ns = re.sub(r"^その後[、,]", "", ns).strip()
                    # 注釈は除外
                    if re.match(r"^（", ns):
                        j += 1
                        continue
                    if _LAT_TAKE_RE.match(ns) or _LAT_REST_RE.match(ns) or _is_static(ns):
                        lat_sents.append(ns)
                        j += 1
                    else:
                        break
                lat_joined = "。".join(lat_sents)
                lat_result = _try_look_and_take(lat_joined, is_spell or after_line, False)
                if lat_result is not None and len(lat_result) == 1:
                    # 複文 LAT として処理成功 → actions を trigger で登録してスキップ
                    for act in lat_result[0]["actions"]:
                        by_trigger.setdefault(trigger, []).append(act)
                    skip_until = j - 1
                    continue
                # 複文 LAT 失敗 → 通常の action_clause で試みる(失敗なら reject)
            # look-resolution スキップ: 自分の山札を見た解決(出す/配置)が modellable でない場合、
            # 残りの解決文がすべて解決型なら、その効果群を under-model(安全)として丸ごと飛ばす。
            if _LOOK_OWN_DECK_RE.match(body) and "相手" not in body:
                tail = [body] + [sentences[k].strip() for k in range(si + 1, len(sentences))]
                if all(_is_look_resolution_sent(s) for s in tail):
                    skip_until = len(sentences) - 1
                    # 解決がこのチャンク内で完結せず次の■に続く場合に備え状態を立てる
                    look_skip_active = True
                    continue
            acts = _parse_action_clause(body)
            if acts is None:
                # 既知のunder-model安全な効果本体ならスキップ(exact-safe)
                body_c = body.rstrip("。")
                if any(re.match(p, body_c) for p in _SAFE_BODY_PATTERNS):
                    continue
                return None
            for trg in (trigger, *extra_triggers):
                by_trigger.setdefault(trg, []).extend([dict(a) for a in acts])
        prev_chunk_trigger = chunk_trigger

    abilities: list[dict[str, Any]] = []
    # S・トリガーは cast/ETB 効果にのみ適用される(攻撃時/破壊時は対象外)
    main_trigger = "on_cast" if is_spell else "on_play"
    for trig, acts in by_trigger.items():
        abilities.append({"trigger": trig, "actions": acts})
        if s_trigger and trig == main_trigger:
            abilities.append({"trigger": "s_trigger", "actions": [dict(a) for a in acts]})
    return abilities
