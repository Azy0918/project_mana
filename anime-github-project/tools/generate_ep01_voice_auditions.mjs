import fs from "node:fs";
import path from "node:path";

const here = path.dirname(new URL(import.meta.url).pathname).replace(/^\/([A-Za-z]:)/, "$1");
const root = path.resolve(here, "..");
const api = "http://127.0.0.1:10101";
const candidatesCsv = path.join(root, "tools", "ep01_voice_audition_candidates.csv");
const linesCsv = path.join(root, "tools", "ep01_voice_audition_lines.csv");
const outDir = path.join(root, "previews", "voice_auditions", "ep01");

const parseCsv = (file) => {
  const text = fs.readFileSync(file, "utf8").replace(/^\uFEFF/, "").trim();
  const [head, ...rows] = text.split(/\r?\n/);
  const headers = head.split(",");
  return rows.filter(Boolean).map((row) => {
    const values = row.split(",");
    return Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""]));
  });
};

const slug = (text) => text.replace(/[^\p{L}\p{N}_-]+/gu, "_").replace(/^_+|_+$/g, "") || "voice";

const audioQuery = async (text, speaker) => {
  const params = new URLSearchParams({ text, speaker: String(speaker) });
  const res = await fetch(`${api}/audio_query?${params}`, { method: "POST" });
  if (!res.ok) throw new Error(`audio_query ${res.status}: ${await res.text()}`);
  return res.json();
};

const synthesize = async (query, speaker) => {
  const params = new URLSearchParams({ speaker: String(speaker) });
  const res = await fetch(`${api}/synthesis?${params}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(query),
  });
  if (!res.ok) throw new Error(`synthesis ${res.status}: ${await res.text()}`);
  return Buffer.from(await res.arrayBuffer());
};

const escapeHtml = (text) =>
  text.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");

fs.mkdirSync(outDir, { recursive: true });
const lines = Object.fromEntries(parseCsv(linesCsv).map((row) => [row.character, row]));
const candidates = parseCsv(candidatesCsv);
const manifest = [];

for (const row of candidates) {
  const line = lines[row.character]?.text;
  if (!line) throw new Error(`missing audition line: ${row.character}`);
  const speaker = Number(row.style_id);
  const query = await audioQuery(line, speaker);
  for (const key of [
    "speedScale",
    "intonationScale",
    "tempoDynamicsScale",
    "pitchScale",
    "volumeScale",
    "prePhonemeLength",
    "postPhonemeLength",
  ]) {
    query[key] = Number(row[key]);
  }
  query.outputSamplingRate = 44100;
  query.outputStereo = false;

  const wav = await synthesize(query, speaker);
  const order = Number(row.order);
  const file = `${slug(row.character)}_${String(order).padStart(2, "0")}_${slug(row.speaker_name)}_${slug(row.style_name)}_${speaker}.wav`;
  fs.writeFileSync(path.join(outDir, file), wav);
  manifest.push({ ...row, file, text: line });
  console.log(`wrote ${file}`);
}

const headers = ["character", "order", "speaker_name", "style_name", "style_id", "file", "text", "notes"];
const manifestCsv = [headers.join(","), ...manifest.map((row) => headers.map((key) => row[key] ?? "").join(","))].join("\n");
fs.writeFileSync(path.join(outDir, "manifest.csv"), `\uFEFF${manifestCsv}`, "utf8");

const html = [
  "<!doctype html>",
  '<html lang="ja">',
  "<head>",
  '<meta charset="utf-8">',
  "<title>第1話 声決め試聴</title>",
  "<style>",
  "body{font-family:system-ui,'Yu Gothic',Meiryo,sans-serif;margin:24px;background:#101316;color:#f4f4f0;}",
  "h1{font-size:24px}h2{margin-top:34px;border-top:1px solid #343a40;padding-top:20px}",
  ".item{padding:12px 0;border-bottom:1px solid #262b31}.meta{color:#b8c0c8;font-size:13px;margin-bottom:6px}",
  "audio{width:100%;max-width:720px}code{color:#d8edff}",
  "</style>",
  "</head><body>",
  "<h1>第1話 声決め試聴</h1>",
  "<p>各キャラごとに、上から順番に聞いて候補を選ぶための一覧です。</p>",
];

let current = "";
for (const item of manifest) {
  if (item.character !== current) {
    current = item.character;
    html.push(`<h2>${escapeHtml(current)}</h2>`);
    html.push(`<p>${escapeHtml(item.text)}</p>`);
  }
  html.push('<div class="item">');
  html.push(
    `<div class="meta"><strong>${escapeHtml(item.order)}.</strong> ${escapeHtml(item.speaker_name)} / ${escapeHtml(item.style_name)} <code>${escapeHtml(item.style_id)}</code> - ${escapeHtml(item.notes)}</div>`,
  );
  html.push(`<audio controls src="${escapeHtml(item.file)}"></audio>`);
  html.push("</div>");
}

html.push("</body></html>");
fs.writeFileSync(path.join(outDir, "index.html"), html.join("\n"), "utf8");
console.log(`wrote ${path.join(outDir, "manifest.csv")}`);
console.log(`wrote ${path.join(outDir, "index.html")}`);
