import fs from "node:fs";
import path from "node:path";

const here = path.dirname(new URL(import.meta.url).pathname).replace(/^\/([A-Za-z]:)/, "$1");
const root = path.resolve(here, "..");

const scriptCsv = path.join(root, "tools", "ep01_full_voice_script.csv");
const castCsv = path.join(root, "tools", "ep01_voice_cast_selected.csv");
const outCsv = path.join(root, "tools", "ep01_full_voice_generation_plan.csv");

const parseCsv = (file) => {
  const text = fs.readFileSync(file, "utf8").replace(/^\uFEFF/, "").trim();
  const [head, ...rows] = text.split(/\r?\n/);
  const headers = head.split(",");
  return rows.filter(Boolean).map((row) => {
    const values = row.split(",");
    return Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""]));
  });
};

const q = (value) => {
  const text = String(value ?? "");
  if (/[",\r\n]/.test(text)) {
    return `"${text.replaceAll('"', '""')}"`;
  }
  return text;
};

const baseCasts = Object.fromEntries(
  parseCsv(castCsv).map((row) => [
    row.character,
    {
      speaker_name: row.speaker_name,
      style_name: row.style_name,
      style_id: row.style_id,
      speedScale: Number(row.speedScale),
      intonationScale: Number(row.intonationScale),
      tempoDynamicsScale: Number(row.tempoDynamicsScale),
      pitchScale: Number(row.pitchScale),
      volumeScale: Number(row.volumeScale),
      prePhonemeLength: Number(row.prePhonemeLength),
      postPhonemeLength: Number(row.postPhonemeLength),
    },
  ]),
);

const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
const round = (value) => Number(value).toFixed(3).replace(/0+$/u, "").replace(/\.$/u, "");

const withDelta = (base, delta = {}) => ({
  ...base,
  speedScale: clamp((base.speedScale ?? 1) + (delta.speed ?? 0), 0.5, 2.0),
  intonationScale: clamp((base.intonationScale ?? 1) + (delta.intonation ?? 0), 0.0, 2.0),
  tempoDynamicsScale: clamp((base.tempoDynamicsScale ?? 1) + (delta.tempo ?? 0), 0.0, 2.0),
  pitchScale: clamp((base.pitchScale ?? 0) + (delta.pitch ?? 0), -0.15, 0.15),
  volumeScale: clamp((base.volumeScale ?? 1) + (delta.volume ?? 0), 0.0, 2.0),
  prePhonemeLength: Math.max(0, (base.prePhonemeLength ?? 0.1) + (delta.pre ?? 0)),
  postPhonemeLength: Math.max(0, (base.postPhonemeLength ?? 0.1) + (delta.post ?? 0)),
});

const deliveryProfiles = {
  quiet_narration: {
    emotion: "静かな叙述",
    delivery_translation: "深夜の空気を前に出し、感情は薄く、語尾に余韻を残す。",
    delta: { speed: -0.02, intonation: -0.03, tempo: -0.03, volume: -0.02, post: 0.1 },
  },
  descriptive_narration: {
    emotion: "状況説明",
    delivery_translation: "映像の補助に徹し、明瞭だが前に出すぎない。",
    delta: { speed: 0, intonation: -0.02, tempo: -0.02, post: 0.02 },
  },
  ominous_narration: {
    emotion: "静かな不穏",
    delivery_translation: "声を少し落として、奇妙さだけを置く。煽らない。",
    delta: { speed: -0.03, intonation: -0.08, tempo: -0.06, pitch: -0.005, volume: -0.03, post: 0.08 },
  },
  warm_narration: {
    emotion: "温かい余韻",
    delivery_translation: "未来食堂の場面だけ柔らかく、少しゆっくり読ませる。",
    delta: { speed: -0.04, intonation: 0.03, tempo: -0.02, pitch: 0.003, volume: 0.02, post: 0.12 },
  },
  receipt_narration: {
    emotion: "レシート読み",
    delivery_translation: "事務的に淡々と読む。ギャグは声で説明しない。",
    delta: { speed: 0.01, intonation: -0.12, tempo: -0.08, pitch: -0.002, post: -0.02 },
  },
  closing_narration: {
    emotion: "締めの余韻",
    delivery_translation: "日常へ戻る寂しさを少しだけ残して、静かに閉じる。",
    delta: { speed: -0.05, intonation: -0.04, tempo: -0.08, pitch: -0.003, volume: -0.02, post: 0.2 },
  },
  takumi_casual: {
    emotion: "軽い雑談",
    delivery_translation: "新人らしく軽く話す。まだ異常は起きていない。",
    delta: { speed: 0, intonation: 0.03, tempo: 0.02, pitch: 0.002 },
  },
  takumi_confused: {
    emotion: "困惑",
    delivery_translation: "理解が追いつかず、少しだけ語尾を浮かせる。",
    delta: { speed: -0.02, intonation: 0.08, tempo: 0.04, pitch: 0.006, post: 0.05 },
  },
  takumi_small: {
    emotion: "小声の受け",
    delivery_translation: "大きく突っ込まず、ぼそっと漏らす。",
    delta: { speed: -0.04, intonation: -0.06, tempo: -0.04, volume: -0.12, pitch: -0.004, post: 0.04 },
  },
  takumi_tsukkomi: {
    emotion: "短いツッコミ",
    delivery_translation: "テンポよく短く返す。叫びにはしない。",
    delta: { speed: 0.05, intonation: 0.1, tempo: 0.08, volume: 0.04, post: -0.02 },
  },
  takumi_strong_tsukkomi: {
    emotion: "強めのツッコミ",
    delivery_translation: "勢いは出すが、音割れしないよう音量は控えめに保つ。",
    delta: { speed: 0.08, intonation: 0.16, tempo: 0.12, pitch: 0.006, volume: 0.05, pre: -0.01, post: 0.01 },
  },
  takumi_decision: {
    emotion: "現実的な即決",
    delivery_translation: "異常を理解したのではなく、金額で即決する現実感を出す。",
    delta: { speed: 0.04, intonation: 0.04, tempo: 0.03, volume: 0.02 },
  },
  takumi_deflated: {
    emotion: "脱力",
    delivery_translation: "力が抜けた低めのツッコミ。余韻を残す。",
    delta: { speed: -0.06, intonation: -0.04, tempo: -0.08, pitch: -0.008, volume: -0.04, post: 0.16 },
  },
  mina_flat: {
    emotion: "低温・淡々",
    delivery_translation: "感情を盛らず、通常業務として読む。",
    delta: { speed: -0.02, intonation: -0.05, tempo: -0.04, volume: -0.02, post: 0.03 },
  },
  mina_rule: {
    emotion: "業務ルール説明",
    delivery_translation: "変なことを言っている自覚なし。社内ルールの説明の温度。",
    delta: { speed: -0.03, intonation: -0.08, tempo: -0.06, pitch: -0.002, post: 0.04 },
  },
  mina_service: {
    emotion: "通常接客",
    delivery_translation: "コンビニ接客の定型文として、まっすぐ読む。",
    delta: { speed: 0, intonation: -0.03, tempo: -0.02, volume: 0.01 },
  },
  mina_cut: {
    emotion: "即答",
    delivery_translation: "短く切る。声は荒げない。",
    delta: { speed: 0.03, intonation: -0.08, tempo: -0.05, post: -0.03 },
  },
  mina_core: {
    emotion: "静かな芯",
    delivery_translation: "この回で唯一、少しだけ人間味を出す。声量は上げない。",
    delta: { speed: -0.05, intonation: 0.02, tempo: -0.04, pitch: -0.003, post: 0.1 },
  },
  register_notice: {
    emotion: "端末通知",
    delivery_translation: "店内端末の案内。感情を消し、一定の速度で読む。",
    delta: { speed: 0, intonation: -0.08, tempo: -0.08, volume: 0.02 },
  },
  register_warning: {
    emotion: "重大警告を事務的に",
    delivery_translation: "内容は重大だが煽らない。数値は聞き取りやすく。",
    delta: { speed: -0.02, intonation: -0.05, tempo: -0.06, volume: 0.04, post: 0.02 },
  },
  register_short: {
    emotion: "短い処理応答",
    delivery_translation: "レジの処理音声として短く平坦に言う。",
    delta: { speed: 0.02, intonation: -0.12, tempo: -0.1, post: -0.04 },
  },
  register_deadpan_joke: {
    emotion: "無機質なボケ",
    delivery_translation: "ボケを演じない。冷たい事実として言う。",
    delta: { speed: -0.03, intonation: -0.1, tempo: -0.1, pitch: -0.004, post: 0.1 },
  },
  salaryman_tired: {
    emotion: "疲労と恐縮",
    delivery_translation: "疲れているが礼儀は残っている。息を少し重くする。",
    delta: { speed: -0.03, intonation: -0.03, tempo: -0.04, volume: -0.02, post: 0.04 },
  },
  salaryman_explain: {
    emotion: "会社員の説明",
    delivery_translation: "言い訳ではなく業務報告。疲れた事務口調。",
    delta: { speed: 0, intonation: -0.02, tempo: -0.02 },
  },
  salaryman_urgent: {
    emotion: "切実",
    delivery_translation: "大げさではなく、始末書を本当に避けたい切実さ。",
    delta: { speed: 0.01, intonation: 0.08, tempo: 0.04, volume: 0.03, post: 0.04 },
  },
  salaryman_soft: {
    emotion: "小さな本音",
    delivery_translation: "会社員としての諦めを短く置く。",
    delta: { speed: -0.05, intonation: -0.04, tempo: -0.05, volume: -0.04, pitch: -0.003 },
  },
  salaryman_emotional: {
    emotion: "抑えた感情",
    delivery_translation: "ここだけ食糧危機の重みを少し出す。泣かせすぎない。",
    delta: { speed: -0.06, intonation: 0.1, tempo: -0.02, volume: 0.02, post: 0.12 },
  },
  zakiyama_plain: {
    emotion: "普通の常連",
    delivery_translation: "奇妙な内容を、コピー機を使いに来た常連の温度で言う。",
    delta: { speed: -0.04, intonation: -0.04, tempo: -0.05, volume: -0.03, post: 0.1 },
  },
  sfx_marker: {
    emotion: "効果音メモ",
    delivery_translation: "音声合成しない。SE設計用のマーカーとして扱う。",
    delta: {},
  },
};

const profileById = {
  ep01_v001: "quiet_narration",
  ep01_v002: "quiet_narration",
  ep01_v003: "descriptive_narration",
  ep01_v004: "takumi_casual",
  ep01_v005: "mina_cut",
  ep01_v006: "takumi_casual",
  ep01_v007: "mina_rule",
  ep01_v008: "takumi_tsukkomi",
  ep01_v009: "mina_rule",
  ep01_v010: "takumi_small",
  ep01_v011: "mina_flat",
  ep01_v012: "takumi_confused",
  ep01_v013: "sfx_marker",
  ep01_v014: "ominous_narration",
  ep01_v015: "register_notice",
  ep01_v016: "takumi_confused",
  ep01_v017: "mina_cut",
  ep01_v018: "takumi_confused",
  ep01_v019: "mina_rule",
  ep01_v020: "takumi_tsukkomi",
  ep01_v021: "sfx_marker",
  ep01_v022: "descriptive_narration",
  ep01_v023: "ominous_narration",
  ep01_v024: "ominous_narration",
  ep01_v025: "salaryman_tired",
  ep01_v026: "mina_service",
  ep01_v027: "salaryman_explain",
  ep01_v028: "takumi_confused",
  ep01_v029: "mina_flat",
  ep01_v030: "takumi_small",
  ep01_v031: "descriptive_narration",
  ep01_v032: "descriptive_narration",
  ep01_v033: "ominous_narration",
  ep01_v034: "register_warning",
  ep01_v035: "register_warning",
  ep01_v036: "takumi_strong_tsukkomi",
  ep01_v037: "salaryman_explain",
  ep01_v038: "salaryman_urgent",
  ep01_v039: "takumi_tsukkomi",
  ep01_v040: "salaryman_soft",
  ep01_v041: "takumi_small",
  ep01_v042: "receipt_narration",
  ep01_v043: "takumi_casual",
  ep01_v044: "mina_cut",
  ep01_v045: "takumi_small",
  ep01_v046: "mina_flat",
  ep01_v047: "takumi_small",
  ep01_v048: "register_short",
  ep01_v049: "register_notice",
  ep01_v050: "register_warning",
  ep01_v051: "takumi_decision",
  ep01_v052: "mina_service",
  ep01_v053: "takumi_strong_tsukkomi",
  ep01_v054: "salaryman_urgent",
  ep01_v055: "takumi_tsukkomi",
  ep01_v056: "takumi_strong_tsukkomi",
  ep01_v057: "sfx_marker",
  ep01_v058: "warm_narration",
  ep01_v059: "warm_narration",
  ep01_v060: "warm_narration",
  ep01_v061: "descriptive_narration",
  ep01_v062: "salaryman_emotional",
  ep01_v063: "register_notice",
  ep01_v064: "register_notice",
  ep01_v065: "mina_core",
  ep01_v066: "takumi_tsukkomi",
  ep01_v067: "register_short",
  ep01_v068: "takumi_tsukkomi",
  ep01_v069: "register_deadpan_joke",
  ep01_v070: "receipt_narration",
  ep01_v071: "receipt_narration",
  ep01_v072: "salaryman_soft",
  ep01_v073: "takumi_deflated",
  ep01_v074: "closing_narration",
  ep01_v075: "receipt_narration",
  ep01_v076: "receipt_narration",
  ep01_v077: "receipt_narration",
  ep01_v078: "receipt_narration",
  ep01_v079: "takumi_deflated",
  ep01_v080: "sfx_marker",
  ep01_v081: "descriptive_narration",
  ep01_v082: "descriptive_narration",
  ep01_v083: "zakiyama_plain",
  ep01_v084: "takumi_confused",
  ep01_v085: "mina_flat",
  ep01_v086: "closing_narration",
  ep01_v087: "closing_narration",
};

const readingById = {
  ep01_v001: "ごぜんにじさんぷん。",
  ep01_v002: "こくどうぞいのこんびには、れいぞうけーすのひくいおとだけでできているみたいにしずかだった。",
  ep01_v003: "しんじんやきんばいとのたくみは、おにぎりだなのまえではいきじかんのしーるをみくらべていた。",
  ep01_v004: "みなさん。はいきのおにぎりって、なんぷんまえからたべていいんですか。",
  ep01_v005: "たべていいとはいってない。",
  ep01_v006: "でもすてるんですよね。",
  ep01_v007: "すてるものとたべていいもののあいだには、てんちょうというふかいたにがある。",
  ep01_v008: "げんじつてきにふかいですね。",
  ep01_v009: "おちるとしふとがへる。",
  ep01_v010: "じごくがきゅうよめいさいにでるたいぷだ。",
  ep01_v011: "にじじゅうごふん、ざっしへんぴん。にじじゅうななふん、だいじゅうさんれじ。",
  ep01_v012: "はい。はい？",
  ep01_v013: "",
  ep01_v014: "たくみがききかえしたしゅんかん、ざっしだなとこぴーきのあいだに、ぎんいろのふるいれじがあらわれた。",
  ep01_v015: "だいじゅうさんれじ。ただいまえいぎょうちゅう。",
  ep01_v016: "ふえた。",
  ep01_v017: "ふえるよ。",
  ep01_v018: "こんびにってよるになるとれじがふえるんですか。",
  ep01_v019: "やきんはだいたいそう。",
  ep01_v020: "ぜったいちがう。",
  ep01_v021: "",
  ep01_v022: "はいってきたのは、くたびれたすーつすがたのおとこだった。",
  ep01_v023: "かたのちいさなえきしょうには、ざんぎょうじかんにひゃくななじゅうろくじかん、とひょうじされている。",
  ep01_v024: "くびもとのとうめいなぱっちが、れじのでんしおんにあわせていちどだけぎんいろにひかった。",
  ep01_v025: "へんぴん、おねがいします。",
  ep01_v026: "れしーとはおもちですか。",
  ep01_v027: "ごじゅうねんごにはっこうされます。",
  ep01_v028: "みなさん。たいおうまにゅあるあります？",
  ep01_v029: "まず、いらっしゃいませ。",
  ep01_v030: "そこからなんですね。",
  ep01_v031: "おとこはふくろからおにぎりをだした。",
  ep01_v032: "ぱっけーじには、かんぜんえいようおにぎり、おもいでのしゃけ。",
  ep01_v033: "せいぞうねんがっぴ、にせんななじゅうよねんろくがつじゅうににち。",
  ep01_v034: "けいこく。このしょうひんはみらいのしょくりょうききかいけつこうほです。",
  ep01_v035: "ごへんぴんによりじんるいせいぞんりつがさんてんにぱーせんとていかします。",
  ep01_v036: "みなさん、ぼくのじきゅうであつかっていいすうじじゃないです。",
  ep01_v037: "うちのかがしけんはんばいまえのしょうひんをかこへごはいそうしまして。",
  ep01_v038: "へんぴんしないとしまつしょがふえます。",
  ep01_v039: "じんるいよりしまつしょをきにしてる。",
  ep01_v040: "かいしゃいんなので。",
  ep01_v041: "せっとくりょくがいやだ。",
  ep01_v042: "だいじゅうさんれじのがめんには、つうじょうへんぴん、じくうへんぴん、そんざいとりけし、あたためる、てんちょうよびだし、とならんでいた。",
  ep01_v043: "てんちょうよびだしがあります。",
  ep01_v044: "おさない。",
  ep01_v045: "なぜ。",
  ep01_v046: "にじいこうはでない。",
  ep01_v047: "てんちょうよびだしのそんざいいぎ。",
  ep01_v048: "のこりじかん、さんぷん。",
  ep01_v049: "にじにじゅっぷんをすぎると、このしょうひんはげんだいてんぽのしんしょうひんとしてていちゃくします。",
  ep01_v050: "しいれげんか、いっこななまんにせんえん。",
  ep01_v051: "へんぴんしましょう。",
  ep01_v052: "こちらのしょうひん、あたためますか。",
  ep01_v053: "このじょうきょうで？",
  ep01_v054: "おねがいします。",
  ep01_v055: "おねがいしますじゃないですよ。",
  ep01_v056: "せかいのぶんきをでんしれんじにいれないでください。",
  ep01_v057: "",
  ep01_v058: "おにぎりがあわくひかり、みらいのしょくどうがうつった。",
  ep01_v059: "からっぽのたな。ながいれつ。",
  ep01_v060: "ちいさなこどもが、そのおにぎりをりょうてでもってわらっている。",
  ep01_v061: "みらいのかいしゃいんはいきをのんだ。",
  ep01_v062: "かいはつきろくです。これが、ちゃんととどけば。",
  ep01_v063: "かねつによりじくうじょうたいがあんていしました。",
  ep01_v064: "りれきめもをにゅうりょくしてください。",
  ep01_v065: "このおにぎりは、ちゃんとつくったほうがいいです。",
  ep01_v066: "ざっくり！",
  ep01_v067: "きろくしました。",
  ep01_v068: "とおるんだ！",
  ep01_v069: "みらいとは、だいたいざつなめものつみかさねです。",
  ep01_v070: "じくうへんぴんがかんりょうし、へんきんがくはひゃくろくじゅうはちえん。",
  ep01_v071: "みらいのかいしゃいんはげんきんでうけとり、さらにほっとこーひーをかった。",
  ep01_v072: "みらいのこーひー、たかいので。",
  ep01_v073: "みらい、いきたくないな。",
  ep01_v074: "ごぜんにじにじゅっぷん。だいじゅうさんれじはきえた。",
  ep01_v075: "のこったれしーとには、こういんじされていた。",
  ep01_v076: "じくうへんぴん、いっけん。れきしめも、いっけん。かんぜんえいようおにぎり、かいはつけいぞく。",
  ep01_v077: "じんるいせいぞんりつ、びぞう。ほっとこーひー、れぎゅらー、いっけん。",
  ep01_v078: "すたっふわりびき、たいしょうがい。",
  ep01_v079: "さいごがいちばんげんじつてきだ。",
  ep01_v080: "",
  ep01_v081: "きんじょのじょうれんらしいおとこがこぴーきへむかった。",
  ep01_v082: "ざきやまたつや、ごじゅうごさい。ねむそうなかおで、ふるいつーりんぐちずをかかえている。",
  ep01_v083: "こぴー、しろくろでいいよ。いろがつくときおくがふえるから。",
  ep01_v084: "このみせ、ふつうのおきゃくさんもへんなんですか。",
  ep01_v085: "やきんだから。",
  ep01_v086: "せかいがすこしだけすくわれても、やきんはおわらない。",
  ep01_v087: "ゆかせいそうも、ざっしへんぴんも、はいきとうろくも、まだのこっている。",
};

const script = parseCsv(scriptCsv);
const headers = [
  "id",
  "cut",
  "role",
  "character",
  "text",
  "reading_hiragana",
  "original_direction",
  "emotion",
  "delivery_translation",
  "speaker_name",
  "style_name",
  "style_id",
  "speedScale",
  "intonationScale",
  "tempoDynamicsScale",
  "pitchScale",
  "volumeScale",
  "prePhonemeLength",
  "postPhonemeLength",
  "pause_after_ms",
  "synthesize",
];

const rows = script.map((line) => {
  const profile = deliveryProfiles[profileById[line.id] ?? "descriptive_narration"];
  const base =
    line.role === "sfx"
      ? {
          speaker_name: "",
          style_name: "",
          style_id: "",
          speedScale: "",
          intonationScale: "",
          tempoDynamicsScale: "",
          pitchScale: "",
          volumeScale: "",
          prePhonemeLength: "",
          postPhonemeLength: "",
        }
      : baseCasts[line.character];

  if (!base) {
    throw new Error(`missing cast for ${line.character} (${line.id})`);
  }

  const tuned = line.role === "sfx" ? base : withDelta(base, profile.delta);
  return {
    id: line.id,
    cut: line.cut,
    role: line.role,
    character: line.character,
    text: line.text,
    reading_hiragana: readingById[line.id] ?? "",
    original_direction: line.direction,
    emotion: profile.emotion,
    delivery_translation: profile.delivery_translation,
    speaker_name: tuned.speaker_name,
    style_name: tuned.style_name,
    style_id: tuned.style_id,
    speedScale: tuned.speedScale === "" ? "" : round(tuned.speedScale),
    intonationScale: tuned.intonationScale === "" ? "" : round(tuned.intonationScale),
    tempoDynamicsScale: tuned.tempoDynamicsScale === "" ? "" : round(tuned.tempoDynamicsScale),
    pitchScale: tuned.pitchScale === "" ? "" : round(tuned.pitchScale),
    volumeScale: tuned.volumeScale === "" ? "" : round(tuned.volumeScale),
    prePhonemeLength: tuned.prePhonemeLength === "" ? "" : round(tuned.prePhonemeLength),
    postPhonemeLength: tuned.postPhonemeLength === "" ? "" : round(tuned.postPhonemeLength),
    pause_after_ms: line.pause_after_ms,
    synthesize: line.role === "sfx" ? "no" : "yes",
  };
});

const csv = [headers.join(","), ...rows.map((row) => headers.map((key) => q(row[key])).join(","))].join("\n");
fs.writeFileSync(outCsv, `\uFEFF${csv}\n`, "utf8");
console.log(`wrote ${outCsv}`);
