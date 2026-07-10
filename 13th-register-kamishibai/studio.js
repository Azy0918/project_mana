/* Episode Studio — self-serve kamishibai authoring tool for 深夜二時の第十三レジ
 * Everything runs client-side. GitHub Contents API is used for all persistence
 * (works from a phone). Audio synthesis calls a local AivisSpeech engine and
 * therefore only works when this page is opened on the PC running it.
 */
(() => {
  "use strict";

  const CUT_COUNT = 20;
  const AIVIS_BASE = "http://localhost:10101";
  const BUILTIN_EPISODES = [
    ["ep01", "第1話 未来のおにぎり、温めますか"],
    ["ep02", "第2話 ナビが未来を案内しました"],
    ["ep03", "第3話 昨日に溶けるアイスクリーム"],
    ["ep04", "第4話 食べ頃ボタン"],
    ["ep05", "第5話 昭和の伝票、まだ未処理です"],
    ["ep06", "第6話 賞味期限が生まれる前のパン"],
    ["ep07", "第7話 宇宙宅配便、店留めです"],
    ["ep08", "第8話 月面店、発注しすぎました"],
    ["ep09", "第9話 銀河ポイントカードはお持ちですか"],
    ["ep10", "第10話 あの会社員、返品済みです"],
    ["ep11", "第11話 第十二レジと第十四レジ"],
    ["ep12", "第12話 午前二時十七分、通常営業です"],
  ];

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  const logEl = () => $("#log");
  function log(msg) {
    const t = new Date().toLocaleTimeString();
    const el = logEl();
    if (el) {
      el.textContent += `[${t}] ${msg}\n`;
      el.scrollTop = el.scrollHeight;
    }
    console.log(msg);
  }

  // ---------- byte / base64 helpers ----------
  function bytesToBase64(bytes) {
    let binary = "";
    const chunk = 0x8000;
    for (let i = 0; i < bytes.length; i += chunk) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
    }
    return btoa(binary);
  }
  function base64ToBytes(b64) {
    const binary = atob(b64.replace(/\n/g, ""));
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    return bytes;
  }
  function textToBytes(str) {
    return new TextEncoder().encode(str);
  }
  function bytesToText(bytes) {
    return new TextDecoder("utf-8").decode(bytes);
  }
  function encodePath(path) {
    return path.split("/").map(encodeURIComponent).join("/");
  }

  // ---------- GitHub Contents API ----------
  function ghConfig() {
    return {
      owner: localStorage.getItem("es_owner") || "azy0918",
      repo: localStorage.getItem("es_repo") || "project_mana",
      branch: localStorage.getItem("es_branch") || "gh-pages",
      token: localStorage.getItem("es_token") || "",
    };
  }
  function ghHeaders() {
    const c = ghConfig();
    return { Authorization: `token ${c.token}`, Accept: "application/vnd.github+json" };
  }
  const BASE_DIR = "13th-register-kamishibai";
  function fullPath(relPath) {
    return `${BASE_DIR}/${relPath}`;
  }
  async function ghGetFile(relPath) {
    const c = ghConfig();
    const url = `https://api.github.com/repos/${c.owner}/${c.repo}/contents/${encodePath(fullPath(relPath))}?ref=${encodeURIComponent(c.branch)}`;
    const res = await fetch(url, { headers: ghHeaders() });
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`GET ${relPath} → ${res.status}`);
    const json = await res.json();
    return { sha: json.sha, bytes: base64ToBytes(json.content) };
  }
  async function ghGetSha(relPath) {
    // Contents APIのファイルGETは1MB超で403になるため、親ディレクトリ一覧からshaを取る
    const c = ghConfig();
    const full = fullPath(relPath);
    const dir = full.split("/").slice(0, -1).join("/");
    const name = full.split("/").pop();
    const url = `https://api.github.com/repos/${c.owner}/${c.repo}/contents/${encodePath(dir)}?ref=${encodeURIComponent(c.branch)}`;
    const res = await fetch(url, { headers: ghHeaders() });
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`GET ${dir} → ${res.status}`);
    const list = await res.json();
    const hit = Array.isArray(list) ? list.find((e) => e.name === name) : null;
    return hit ? hit.sha : null;
  }
  async function ghPutFile(relPath, bytes, message) {
    const c = ghConfig();
    const sha = await ghGetSha(relPath);
    const url = `https://api.github.com/repos/${c.owner}/${c.repo}/contents/${encodePath(fullPath(relPath))}`;
    const body = { message, content: bytesToBase64(bytes), branch: c.branch };
    if (sha) body.sha = sha;
    const res = await fetch(url, {
      method: "PUT",
      headers: { ...ghHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const t = await res.text();
      let msg = `PUT ${relPath} → ${res.status} ${t.slice(0, 300)}`;
      if (res.status === 403 && /not accessible by personal access token/i.test(t)) {
        msg += " ｜対処: Fine-grained PATの「Repository access」に Azy0918/project_mana を追加し、「Permissions→Contents」を Read and write にしてください";
      }
      throw new Error(msg);
    }
    return res.json();
  }
  async function ghPutJSON(relPath, obj, message) {
    return ghPutFile(relPath, textToBytes(JSON.stringify(obj, null, 2)), message);
  }
  async function ghGetJSON(relPath) {
    const f = await ghGetFile(relPath);
    if (!f) return null;
    return JSON.parse(bytesToText(f.bytes));
  }
  async function ghCheckConnection() {
    const c = ghConfig();
    if (!c.token) throw new Error("トークンが未入力です");
    const res = await fetch(`https://api.github.com/repos/${c.owner}/${c.repo}`, { headers: ghHeaders() });
    if (!res.ok) throw new Error(`repo check → ${res.status}`);
    const json = await res.json();
    // 公開リポジトリは無権限トークンでも読めるため、書き込み権限を明示チェック
    if (!json.permissions || !json.permissions.push) {
      throw new Error("このトークンには書き込み権限がありません。Fine-grained PATの「Repository access」に対象リポジトリを追加し、Contents権限を Read and write にしてください");
    }
    return json;
  }

  // ---------- WAV helpers (generic chunk scan, no fixed offsets) ----------
  function parseWav(buf) {
    const dv = new DataView(buf);
    let pos = 12; // skip "RIFF"(4) size(4) "WAVE"(4)
    let fmt = null;
    let dataOffset = -1;
    let dataSize = 0;
    while (pos + 8 <= buf.byteLength) {
      const id = String.fromCharCode(dv.getUint8(pos), dv.getUint8(pos + 1), dv.getUint8(pos + 2), dv.getUint8(pos + 3));
      const size = dv.getUint32(pos + 4, true);
      if (id === "fmt ") {
        fmt = {
          audioFormat: dv.getUint16(pos + 8, true),
          channels: dv.getUint16(pos + 10, true),
          sampleRate: dv.getUint32(pos + 12, true),
          bitsPerSample: dv.getUint16(pos + 22, true),
        };
      } else if (id === "data") {
        dataOffset = pos + 8;
        dataSize = size;
      }
      pos += 8 + size + (size % 2);
    }
    return { fmt, dataOffset, dataSize };
  }
  function wavDurationSec(buf) {
    const { fmt, dataSize } = parseWav(buf);
    if (!fmt) return 0;
    return dataSize / (fmt.sampleRate * fmt.channels * (fmt.bitsPerSample / 8));
  }
  function writeAscii(dv, offset, str) {
    for (let i = 0; i < str.length; i += 1) dv.setUint8(offset + i, str.charCodeAt(i));
  }
  function buildWav(fmt, pcmBytes) {
    const blockAlign = fmt.channels * (fmt.bitsPerSample / 8);
    const byteRate = fmt.sampleRate * blockAlign;
    const out = new Uint8Array(44 + pcmBytes.length);
    const dv = new DataView(out.buffer);
    writeAscii(dv, 0, "RIFF");
    dv.setUint32(4, 36 + pcmBytes.length, true);
    writeAscii(dv, 8, "WAVE");
    writeAscii(dv, 12, "fmt ");
    dv.setUint32(16, 16, true);
    dv.setUint16(20, 1, true);
    dv.setUint16(22, fmt.channels, true);
    dv.setUint32(24, fmt.sampleRate, true);
    dv.setUint32(28, byteRate, true);
    dv.setUint16(32, blockAlign, true);
    dv.setUint16(34, fmt.bitsPerSample, true);
    writeAscii(dv, 36, "data");
    dv.setUint32(40, pcmBytes.length, true);
    out.set(pcmBytes, 44);
    return out;
  }
  function silenceBytes(ms, fmt) {
    const samples = Math.round((fmt.sampleRate * ms) / 1000);
    return new Uint8Array(samples * fmt.channels * (fmt.bitsPerSample / 8));
  }
  // clips: [{buf: ArrayBuffer, pauseMs: number, id: string}]
  function concatClips(clips) {
    const first = parseWav(clips[0].buf);
    const fmt = first.fmt;
    const parts = [];
    const timings = {};
    let cursorSec = 0;
    clips.forEach((c) => {
      const { dataOffset, dataSize, fmt: f2 } = parseWav(c.buf);
      const pcm = new Uint8Array(c.buf, dataOffset, dataSize);
      parts.push(pcm);
      const dur = dataSize / (f2.sampleRate * f2.channels * (f2.bitsPerSample / 8));
      timings[c.id] = { start: cursorSec, end: cursorSec + dur };
      cursorSec += dur;
      if (c.pauseMs > 0) {
        parts.push(silenceBytes(c.pauseMs, f2));
        cursorSec += c.pauseMs / 1000;
      }
    });
    const total = parts.reduce((a, p) => a + p.length, 0);
    const merged = new Uint8Array(total);
    let off = 0;
    parts.forEach((p) => {
      merged.set(p, off);
      off += p.length;
    });
    return { wavBytes: buildWav(fmt, merged), timings, totalSec: cursorSec };
  }

  // ---------- AivisSpeech ----------
  async function aivisPing() {
    const res = await fetch(`${AIVIS_BASE}/version`, { cache: "no-store" });
    if (!res.ok) throw new Error(String(res.status));
    return res.json();
  }
  async function aivisSpeakers() {
    const res = await fetch(`${AIVIS_BASE}/speakers`, { cache: "no-store" });
    if (!res.ok) throw new Error(String(res.status));
    return res.json();
  }
  async function aivisSynthesize(text, styleId) {
    const qUrl = `${AIVIS_BASE}/audio_query?${new URLSearchParams({ text, speaker: String(styleId) })}`;
    const qRes = await fetch(qUrl, { method: "POST" });
    if (!qRes.ok) throw new Error(`audio_query → ${qRes.status}`);
    const queryJson = await qRes.json();
    const sRes = await fetch(`${AIVIS_BASE}/synthesis?speaker=${encodeURIComponent(styleId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(queryJson),
    });
    if (!sRes.ok) throw new Error(`synthesis → ${sRes.status}`);
    return sRes.arrayBuffer();
  }

  // ---------- CSV ----------
  function parseCSV(text) {
    const rows = [];
    let row = [];
    let field = "";
    let inQuotes = false;
    const pushField = () => {
      row.push(field);
      field = "";
    };
    const pushRow = () => {
      pushField();
      rows.push(row);
      row = [];
    };
    for (let i = 0; i < text.length; i += 1) {
      const c = text[i];
      if (inQuotes) {
        if (c === '"') {
          if (text[i + 1] === '"') {
            field += '"';
            i += 1;
          } else inQuotes = false;
        } else field += c;
      } else if (c === '"') inQuotes = true;
      else if (c === ",") pushField();
      else if (c === "\n") pushRow();
      else if (c === "\r") {
        /* skip */
      } else field += c;
    }
    if (field.length || row.length) pushRow();
    if (!rows.length) return [];
    const header = rows[0];
    return rows
      .slice(1)
      .filter((r) => r.some((v) => v !== ""))
      .map((r) => Object.fromEntries(header.map((h, i) => [h.trim(), r[i] ?? ""])));
  }
  function toCSV(rows, columns) {
    const esc = (v) => {
      const s = String(v ?? "");
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const lines = [columns.join(",")];
    rows.forEach((r) => lines.push(columns.map((c) => esc(r[c])).join(",")));
    return lines.join("\n");
  }

  // ---------- state ----------
  const state = {
    epId: null,
    lines: [], // {id, speaker, text, reading, pauseMs, cut, styleId, speakerName, clipBytes?, generated}
    cuts: [], // 20 entries {index, title, prompt, image, manualStart}
    fullAudioBytes: null,
    timings: {}, // id -> {start,end} once generated/committed
  };

  function newLine(seq, cut) {
    return {
      id: `${state.epId}_v${String(seq).padStart(3, "0")}`,
      speaker: "ナレーション",
      text: "",
      reading: "",
      pauseMs: 400,
      cut: cut || 1,
      styleId: "",
      speakerName: "",
      generated: false,
    };
  }
  function emptyCuts() {
    return Array.from({ length: CUT_COUNT }, (_, i) => ({
      index: i + 1,
      title: "",
      prompt: "",
      image: `assets/scenes/planned/${state.epId}_vc${String(i + 1).padStart(2, "0")}.png`,
      manualStart: "",
    }));
  }

  function epFiles(epId) {
    if (epId === "ep01") {
      return {
        manifest: "assets/manifest_reading_hiragana_mina_mao.json",
        visualCutPlan: "visual_cut_plan.json",
        imageAssignment: null,
        sceneManifest: "scene_manifest.json",
        fullAudio: "assets/ep01_full_voice_reading_hiragana_mina_mao.wav",
      };
    }
    return {
      manifest: `assets/manifest_reading_hiragana_${epId}.json`,
      visualCutPlan: `visual_cut_plan_${epId}.json`,
      imageAssignment: `image_assignment_${epId}.json`,
      sceneManifest: `scene_manifest_${epId}.json`,
      fullAudio: `assets/${epId}_full_voice_reading_hiragana.wav`,
    };
  }

  async function loadEpisode(epId) {
    state.epId = epId;
    state.timings = {};
    state.fullAudioBytes = null;
    const files = epFiles(epId);
    const c = ghConfig();
    if (!c.owner || !c.repo || !c.token) {
      throw new Error("GitHub接続が未設定です。設定タブでOwner/Repo/Tokenを入力し「保存して接続確認」を押してください。");
    }
    const [manifest, visualCutPlan] = await Promise.all([
      ghGetJSON(files.manifest),
      ghGetJSON(files.visualCutPlan),
    ]);

    if (!manifest || !manifest.length) {
      state.lines = [newLine(1, 1)];
      state.cuts = emptyCuts();
      log(`${epId}: 既存データなし。新規として初期化しました。`);
      return;
    }

    const idIndex = {};
    manifest.forEach((m, i) => {
      idIndex[m.id] = i;
    });
    const cuts = emptyCuts();
    (visualCutPlan || []).forEach((vc, i) => {
      if (i >= CUT_COUNT) return;
      cuts[i] = {
        index: i + 1,
        title: vc.title || "",
        prompt: vc.prompt || "",
        image: vc.plannedImage || cuts[i].image,
        manualStart: "",
      };
    });
    const cutForLine = (i) => {
      for (let ci = 0; ci < (visualCutPlan || []).length && ci < CUT_COUNT; ci += 1) {
        const vc = visualCutPlan[ci];
        const startIdx = idIndex[vc.lineStart];
        const endIdx = idIndex[vc.lineEnd];
        if (startIdx !== undefined && endIdx !== undefined && i >= startIdx && i <= endIdx) return ci + 1;
      }
      return 1;
    };
    state.lines = manifest.map((m, i) => ({
      id: m.id,
      speaker: m.character || "",
      text: m.text || "",
      reading: m.synthesis_text || m.text || "",
      pauseMs: m.pause_after_ms ?? 400,
      cut: cutForLine(i),
      styleId: m.style_id != null ? String(m.style_id) : "",
      speakerName: m.speaker_name || "",
      generated: true,
    }));
    state.cuts = cuts;
    log(`${epId}: ${state.lines.length}行 / ${(visualCutPlan || []).length}カットを読み込みました。`);
  }

  function nextEpNum() {
    let max = 12;
    BUILTIN_EPISODES.forEach(([id]) => {
      const n = parseInt(id.replace("ep", ""), 10);
      if (n > max) max = n;
    });
    return max + 1;
  }

  // ---------- rendering: dialogue tab ----------
  function renderLines() {
    const list = $("#lineList");
    $("#lineCount").textContent = `（${state.lines.length}行）`;
    list.innerHTML = state.lines
      .map(
        (l, i) => `
      <div class="line-card" data-i="${i}">
        <div class="line-head">
          <span class="idtag">${l.id}</span>
          <input class="f-speaker" value="${escAttr(l.speaker)}" placeholder="話者" style="width:110px">
          <select class="f-cut">${Array.from({ length: CUT_COUNT }, (_, c) => `<option value="${c + 1}" ${l.cut === c + 1 ? "selected" : ""}>カット${c + 1}</option>`).join("")}</select>
          <input class="f-pause" type="number" value="${l.pauseMs}" title="ポーズ(ms)" style="width:80px">
          <span class="muted">ms</span>
          ${l.generated ? '<span class="badge ok">音声あり</span>' : '<span class="badge warn">未生成</span>'}
        </div>
        <label>セリフ（表示テキスト）</label>
        <textarea class="f-text">${escHtml(l.text)}</textarea>
        <label style="margin-top:4px">読み方（TTS用・空欄ならセリフをそのまま使用）</label>
        <textarea class="f-reading">${escHtml(l.reading)}</textarea>
        <div class="line-ctl">
          <button class="dup" title="複製">複製</button>
          <button class="del danger" title="削除">削除</button>
          <button class="up" title="上へ">↑</button>
          <button class="down" title="下へ">↓</button>
        </div>
      </div>`
      )
      .join("");

    list.querySelectorAll(".line-card").forEach((card) => {
      const i = Number(card.dataset.i);
      card.querySelector(".f-speaker").addEventListener("input", (e) => (state.lines[i].speaker = e.target.value));
      card.querySelector(".f-cut").addEventListener("change", (e) => (state.lines[i].cut = Number(e.target.value)));
      card.querySelector(".f-pause").addEventListener("input", (e) => (state.lines[i].pauseMs = Number(e.target.value) || 0));
      card.querySelector(".f-text").addEventListener("input", (e) => {
        state.lines[i].text = e.target.value;
        state.lines[i].generated = false;
      });
      card.querySelector(".f-reading").addEventListener("input", (e) => {
        state.lines[i].reading = e.target.value;
        state.lines[i].generated = false;
      });
      card.querySelector(".dup").addEventListener("click", () => {
        const copy = { ...state.lines[i], id: `${state.epId}_v${String(state.lines.length + 1).padStart(3, "0")}`, generated: false };
        state.lines.splice(i + 1, 0, copy);
        renumberLines();
        renderLines();
      });
      card.querySelector(".del").addEventListener("click", () => {
        if (state.lines.length <= 1) return;
        state.lines.splice(i, 1);
        renumberLines();
        renderLines();
      });
      card.querySelector(".up").addEventListener("click", () => {
        if (i === 0) return;
        [state.lines[i - 1], state.lines[i]] = [state.lines[i], state.lines[i - 1]];
        renderLines();
      });
      card.querySelector(".down").addEventListener("click", () => {
        if (i === state.lines.length - 1) return;
        [state.lines[i + 1], state.lines[i]] = [state.lines[i], state.lines[i + 1]];
        renderLines();
      });
    });
  }
  function renumberLines() {
    state.lines.forEach((l, i) => {
      l.id = `${state.epId}_v${String(i + 1).padStart(3, "0")}`;
    });
  }
  function escHtml(s) {
    return String(s ?? "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  }
  function escAttr(s) {
    return escHtml(s).replace(/"/g, "&quot;");
  }

  // ---------- rendering: images tab ----------
  function renderCuts() {
    const grid = $("#cutGrid");
    const rawBase = () => {
      const c = ghConfig();
      return `https://raw.githubusercontent.com/${c.owner}/${c.repo}/${c.branch}/${BASE_DIR}/`;
    };
    grid.innerHTML = state.cuts
      .map(
        (c, i) => `
      <div class="cut-card" data-i="${i}">
        <img loading="lazy" src="${rawBase()}${c.image}?t=${Date.now()}" alt="cut ${c.index}"
             onerror="this.style.opacity=0.25">
        <div class="path">保存先: ${c.image}</div>
        <label>タイトル</label>
        <input class="c-title" value="${escAttr(c.title)}">
        <label style="margin-top:4px">生成プロンプト（codex等へ渡す）</label>
        <textarea class="c-prompt">${escHtml(c.prompt)}</textarea>
        <div class="row" style="margin-top:6px">
          <div class="col"><label>開始(秒・空欄=自動)</label><input class="c-start" type="number" step="0.1" value="${c.manualStart}"></div>
          <div class="col flex1"><label>画像を差し替え</label><input class="c-file" type="file" accept="image/*"></div>
        </div>
        <div class="muted c-status" style="margin-top:4px"></div>
      </div>`
      )
      .join("");
    grid.querySelectorAll(".cut-card").forEach((card) => {
      const i = Number(card.dataset.i);
      card.querySelector(".c-title").addEventListener("input", (e) => (state.cuts[i].title = e.target.value));
      card.querySelector(".c-prompt").addEventListener("input", (e) => (state.cuts[i].prompt = e.target.value));
      card.querySelector(".c-start").addEventListener("input", (e) => (state.cuts[i].manualStart = e.target.value));
      card.querySelector(".c-file").addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const status = card.querySelector(".c-status");
        const bytes = new Uint8Array(await file.arrayBuffer());
        const ext = (file.name.match(/\.\w+$/) || [".png"])[0];
        const path = state.cuts[i].image.replace(/\.\w+$/, ext);
        state.cuts[i].image = path;
        status.textContent = `アップロード中… (${Math.round(bytes.length / 1024)} KB)`;
        try {
          await ghPutFile(path, bytes, `${state.epId} vc${String(i + 1).padStart(2, "0")} 画像を更新`);
          log(`画像を保存しました: ${path}`);
          renderCuts();
        } catch (err) {
          status.textContent = `❌ 保存失敗: ${err.message}`;
          log(`画像の保存に失敗: ${err.message}`);
        }
      });
    });
  }

  // ---------- rendering: audio tab ----------
  function renderAudioLines() {
    const list = $("#audioLineList");
    list.innerHTML = state.lines
      .map(
        (l, i) => `
      <div class="line-card" data-i="${i}">
        <div class="line-head">
          <span class="idtag">${l.id}</span>
          <span class="muted">${escHtml(l.speaker)}</span>
          <input class="a-style" placeholder="AivisSpeech style_id" value="${escAttr(l.styleId)}" style="width:170px">
          <span id="genstat-${i}" class="badge ${l.generated ? "ok" : "warn"}">${l.generated ? "生成済み" : "未生成"}</span>
        </div>
        <div class="muted" style="font-size:12px">${escHtml(l.reading || l.text)}</div>
        <div class="line-ctl">
          <button class="gen-one go">この行だけ生成</button>
          <audio class="preview-audio" controls style="height:30px;display:${l.clipUrl ? "inline-block" : "none"}" src="${l.clipUrl || ""}"></audio>
        </div>
      </div>`
      )
      .join("");
    list.querySelectorAll(".line-card").forEach((card) => {
      const i = Number(card.dataset.i);
      card.querySelector(".a-style").addEventListener("input", (e) => (state.lines[i].styleId = e.target.value));
      card.querySelector(".gen-one").addEventListener("click", () => generateLine(i));
    });
  }

  function diagnoseAivis(err) {
    const m = String((err && err.message) || err);
    if (/Failed to fetch|NetworkError|load failed/i.test(m)) {
      return "AivisSpeech未接続かCORS未許可。PCでエンジンを --cors_policy_mode all 付きで起動してください";
    }
    if (/\b403\b/.test(m)) return "エンジンが拒否(403)。--cors_policy_mode all で起動し直してください";
    return m;
  }

  function setGenBadge(i, text, cls) {
    const el = $(`#genstat-${i}`);
    if (el) {
      el.textContent = text;
      el.className = `badge ${cls}`;
    }
  }

  async function generateLine(i) {
    const l = state.lines[i];
    if (!l.styleId) {
      setGenBadge(i, "style_id未設定", "bad");
      log(`${l.id}: style_id が未設定です。`);
      return false;
    }
    setGenBadge(i, "合成中…", "warn");
    try {
      const buf = await aivisSynthesize(l.reading || l.text, l.styleId);
      l.clipBuf = buf;
      l.clipUrl = URL.createObjectURL(new Blob([buf], { type: "audio/wav" }));
      l.generated = true;
      log(`${l.id}: 生成完了 (${wavDurationSec(buf).toFixed(2)}s)`);
      renderAudioLines();
      return true;
    } catch (err) {
      setGenBadge(i, `✕ ${diagnoseAivis(err)}`, "bad");
      log(`${l.id}: 生成失敗 — ${err.message}`);
      return false;
    }
  }

  async function generateAll(force) {
    const bar = $("#genProgressBar");
    const total = state.lines.length;
    let ok = 0;
    let fail = 0;
    for (let i = 0; i < state.lines.length; i += 1) {
      const l = state.lines[i];
      if (!force && l.generated && l.clipBuf) {
        ok += 1;
        continue;
      }
      $("#genProgress").textContent = `${l.id} 生成中… (${ok + fail + 1}/${total})`;
      // eslint-disable-next-line no-await-in-loop
      const success = await generateLine(i);
      if (success) ok += 1;
      else fail += 1;
      bar.style.width = `${Math.round(((ok + fail) / total) * 100)}%`;
      if (fail >= 3 && ok === 0) {
        $("#genProgress").textContent = `❌ 中断: 連続失敗。AivisSpeechエンジンの起動とCORS許可(--cors_policy_mode all)を確認してください`;
        return;
      }
    }
    $("#genProgress").textContent = fail
      ? `⚠ 完了: 成功${ok} / 失敗${fail} — 失敗行のバッジを確認してください`
      : `✅ 完了: ${ok}/${total} 全行生成済み。下の「結合してGitHubへコミット」で公開できます`;
  }

  function buildSceneManifest() {
    // natural sequential timing from generated clips (or rough estimate before generation)
    const estimate = (l) => Math.max(0.6, (l.reading || l.text || "").length * 0.14);
    let cursor = 0;
    const naturalStart = {};
    const naturalEnd = {};
    state.lines.forEach((l) => {
      const dur = l.clipBuf ? wavDurationSec(l.clipBuf) : state.timings[l.id] ? state.timings[l.id].end - state.timings[l.id].start : estimate(l);
      naturalStart[l.id] = cursor;
      cursor += dur;
      naturalEnd[l.id] = cursor;
      cursor += (l.pauseMs || 0) / 1000;
    });

    // resolve cut start times: manual override, else natural start of first line in that cut
    const cutStart = {};
    state.cuts.forEach((c) => {
      if (c.manualStart !== "" && c.manualStart != null && !Number.isNaN(Number(c.manualStart))) {
        cutStart[c.index] = Number(c.manualStart);
      } else {
        const firstLine = state.lines.find((l) => l.cut === c.index);
        cutStart[c.index] = firstLine ? naturalStart[firstLine.id] : null;
      }
    });
    const orderedCutIndexes = state.cuts.map((c) => c.index).filter((idx) => cutStart[idx] != null).sort((a, b) => cutStart[a] - cutStart[b]);

    const imageForTime = (t) => {
      let chosen = state.cuts[0];
      for (let k = 0; k < orderedCutIndexes.length; k += 1) {
        const idx = orderedCutIndexes[k];
        if (cutStart[idx] <= t) chosen = state.cuts[idx - 1];
        else break;
      }
      return chosen;
    };

    const scenes = state.lines.map((l, i) => {
      const cut = state.cuts[l.cut - 1];
      const startForImage = imageForTime(naturalStart[l.id]);
      return {
        id: l.id,
        cut: `${state.epId}_${String(i + 1).padStart(3, "0")}`,
        visualCutId: `vc${String((startForImage || cut).index).padStart(2, "0")}`,
        visualCutTitle: (startForImage || cut).title,
        visualCutIndex: (startForImage || cut).index,
        start: Number(naturalStart[l.id].toFixed(3)),
        end: Number(naturalEnd[l.id].toFixed(3)),
        image: (startForImage || cut).image,
        plannedImage: (startForImage || cut).image,
        fallbackImage: (startForImage || cut).image,
        imagePrompt: (startForImage || cut).prompt,
        speaker: l.speaker,
        dialogue: l.text,
        log: [],
        visualLabel: `${String((startForImage || cut).index).padStart(2, "0")}/${CUT_COUNT}　${(startForImage || cut).title}`,
        progressLabel: `${String(i + 1).padStart(2, "0")}/${state.lines.length}　${l.speaker}`,
      };
    });
    return scenes;
  }

  async function commitAudio() {
    const missing = state.lines.filter((l) => !l.clipBuf);
    if (missing.length) {
      throw new Error(`未生成の行が${missing.length}件あります。先に音声タブで一括生成してください（このブラウザで生成した音声だけが結合対象です）`);
    }
    const clips = state.lines.map((l) => ({ id: l.id, buf: l.clipBuf, pauseMs: l.pauseMs }));
    const { wavBytes, timings } = concatClips(clips);
    state.timings = timings;
    state.fullAudioBytes = wavBytes;
    const files = epFiles(state.epId);
    log("結合音声・manifest・scene_manifestをコミット中…");
    await ghPutFile(files.fullAudio, wavBytes, `${state.epId} 音声を更新`);
    await ghPutJSON(
      files.manifest,
      state.lines.map((l, i) => ({
        id: l.id,
        cut: `${state.epId}_${String(i + 1).padStart(3, "0")}`,
        visualCutId: `vc${String(l.cut).padStart(2, "0")}`,
        character: l.speaker,
        speaker_name: l.speakerName,
        style_name: "",
        style_id: l.styleId,
        text: l.text,
        synthesis_text: l.reading || l.text,
        synthesis_source: "aivis_studio",
        pause_after_ms: l.pauseMs,
        clip: `${BASE_DIR}/assets/clips_${state.epId}/${l.id}.wav`,
      })),
      `${state.epId} manifest を更新`
    );
    await ghPutJSON(files.sceneManifest, buildSceneManifest(), `${state.epId} scene_manifest を更新`);
    log("コミット完了。");
  }

  // ---------- images/cuts save ----------
  async function saveCuts() {
    const files = epFiles(state.epId);
    const visualCutPlan = state.cuts.map((c) => {
      const linesInCut = state.lines.filter((l) => l.cut === c.index);
      return {
        visualCutId: `vc${String(c.index).padStart(2, "0")}`,
        lineStart: linesInCut[0] ? linesInCut[0].id : "",
        lineEnd: linesInCut.length ? linesInCut[linesInCut.length - 1].id : "",
        title: c.title,
        plannedImage: c.image,
        fallbackImage: c.image,
        prompt: c.prompt,
        characterIds: [],
        characterReferenceImages: [],
      };
    });
    await ghPutJSON(files.visualCutPlan, visualCutPlan, `${state.epId} 画像カット情報を更新`);
    if (files.imageAssignment) {
      const assignments = {};
      state.lines.forEach((l) => {
        assignments[l.id] = state.cuts[l.cut - 1].image;
      });
      await ghPutJSON(files.imageAssignment, { version: 1, episode: state.epId, assignments }, `${state.epId} 画像割当を更新`);
    }
    log("カット情報を保存しました。");
  }

  // ---------- dialogue save ----------
  async function saveDialogue() {
    await saveCuts();
    const files = epFiles(state.epId);
    await ghPutJSON(
      files.manifest,
      state.lines.map((l, i) => ({
        id: l.id,
        cut: `${state.epId}_${String(i + 1).padStart(3, "0")}`,
        visualCutId: `vc${String(l.cut).padStart(2, "0")}`,
        character: l.speaker,
        speaker_name: l.speakerName,
        style_name: "",
        style_id: l.styleId,
        text: l.text,
        synthesis_text: l.reading || l.text,
        synthesis_source: "aivis_studio",
        pause_after_ms: l.pauseMs,
        clip: `${BASE_DIR}/assets/clips_${state.epId}/${l.id}.wav`,
      })),
      `${state.epId} セリフを更新`
    );
    log("セリフを保存しました。");
  }

  // ---------- publish (register new episode into index.html) ----------
  async function patchIndexHtmlAddEpisode(epId, label) {
    const f = await ghGetFile("index.html");
    if (!f) throw new Error("index.html が見つかりません");
    const text = bytesToText(f.bytes);
    const files = epFiles(epId);
    const entry = `      {
        id: "${epId}",
        label: "${label}",
        title: "深夜二時の第十三レジ ${label}",
        badge: "${label}",
        audio: "./${files.fullAudio}",
        manifest: "./${files.sceneManifest}",
        fallbackImage: "./${state.cuts[0].image}",
        links: [
          { href: "./${files.fullAudio}", text: "音声を保存", download: true },
          { href: "./${files.manifest}", text: "manifest" },
          { href: "./${files.sceneManifest}", text: "line_manifest", download: true }
        ],
        miniLinks: [
          { href: "./assets/character_storyboard_sheet.jpg", text: "キャラ表" }
        ]
      },\n`;
    const anchor = "\n    ];\n\n    const buildLinks";
    if (!text.includes(anchor)) throw new Error("index.html の差し込み位置が見つかりません（手動確認が必要です）");
    if (text.includes(`id: "${epId}"`)) {
      log(`index.html には既に ${epId} が登録済みです。`);
      return;
    }
    const patched = text.replace(anchor, `\n${entry}    ];\n\n    const buildLinks`);
    // sanity check: must still be syntactically parseable as part of an array-of-objects literal
    new Function(`return [${entry.replace(/,\s*$/, "")}]`);
    await ghPutFile("index.html", textToBytes(patched), `index.html: ${epId} を追加`);
    log(`index.html に ${epId} を登録しました。`);
  }

  async function publishPlayer() {
    const status = $("#publishStatus");
    try {
      status.textContent = "保存中…";
      await saveCuts();
      const files = epFiles(state.epId);
      await ghPutJSON(files.sceneManifest, buildSceneManifest(), `${state.epId} scene_manifest を公開`);
      const label = BUILTIN_EPISODES.find(([id]) => id === state.epId)?.[1] || $("#newEpTitle").value || state.epId;
      await patchIndexHtmlAddEpisode(state.epId, label);
      const c = ghConfig();
      status.textContent = `公開しました: https://${c.owner}.github.io/${c.repo}/${BASE_DIR}/index.html`;
    } catch (err) {
      status.textContent = `失敗: ${err.message}`;
      log(`公開失敗: ${err.message}`);
    }
  }

  // ---------- preview ----------
  async function renderPreview() {
    let i = 0;
    const img = $("#prevImg");
    const speaker = $("#prevSpeaker");
    const text = $("#prevText");
    const meta = $("#prevMeta");
    const audio = $("#prevAudio");
    const rawBase = () => {
      const c = ghConfig();
      return `https://raw.githubusercontent.com/${c.owner}/${c.repo}/${c.branch}/${BASE_DIR}/`;
    };
    let scenes;
    let source;
    if (state.fullAudioBytes) {
      // このセッションで生成・結合した未公開音声を使う
      scenes = buildSceneManifest();
      audio.src = URL.createObjectURL(new Blob([state.fullAudioBytes], { type: "audio/wav" }));
      source = "未公開の生成音声";
    } else {
      // 公開済みの scene_manifest + 結合wav にフォールバック
      const files = epFiles(state.epId);
      meta.textContent = "公開済みデータを読み込み中…";
      try {
        const res = await fetch(rawBase() + files.sceneManifest + "?t=" + Date.now(), { cache: "no-store" });
        if (!res.ok) throw new Error(`scene_manifest ${res.status}`);
        scenes = await res.json();
        audio.src = rawBase() + files.fullAudio;
        source = "公開済みデータ";
      } catch (err) {
        meta.textContent = `❌ 公開済みデータの読み込みに失敗: ${err.message}（未公開の話数は先に音声を生成してください）`;
        return;
      }
    }
    function show(idx) {
      const s = scenes[idx];
      if (!s) return;
      img.src = rawBase() + s.image;
      speaker.textContent = s.speaker;
      text.textContent = s.dialogue;
      meta.textContent = `${idx + 1}/${scenes.length} ｜ ${Number(s.start).toFixed(1)}s - ${Number(s.end).toFixed(1)}s ｜ ${s.visualCutId} ｜ ${source}`;
    }
    show(0);
    audio.ontimeupdate = () => {
      const t = audio.currentTime;
      const idx = scenes.findIndex((s) => t >= s.start && t < s.end);
      if (idx >= 0 && idx !== i) {
        i = idx;
        show(idx);
      }
    };
  }

  // ---------- video export ----------
  async function renderVideo() {
    const status = $("#videoStatus");
    const bar = $("#videoProgressBar");
    if (!state.fullAudioBytes) {
      status.textContent = "先に音声を結合してください（音声タブ→結合してGitHubへコミット、または一括生成のみでもOK）。";
      return;
    }
    const [w, h] = $("#videoRes").value.split("x").map(Number);
    const canvas = $("#videoCanvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    const scenes = buildSceneManifest();
    const rawBase = () => {
      const c = ghConfig();
      return `https://raw.githubusercontent.com/${c.owner}/${c.repo}/${c.branch}/${BASE_DIR}/`;
    };
    const imgCache = {};
    async function loadImg(path) {
      if (imgCache[path]) return imgCache[path];
      const im = new Image();
      im.crossOrigin = "anonymous";
      im.src = rawBase() + path;
      await new Promise((resolve) => {
        im.onload = resolve;
        im.onerror = resolve;
      });
      imgCache[path] = im;
      return im;
    }
    status.textContent = "画像を先読み中…";
    await Promise.all(scenes.map((s) => loadImg(s.image)));

    const audioBlob = new Blob([state.fullAudioBytes], { type: "audio/wav" });
    const audioEl = new Audio(URL.createObjectURL(audioBlob));
    await new Promise((resolve) => {
      audioEl.onloadedmetadata = resolve;
    });

    const audioCtx = new AudioContext();
    const srcNode = audioCtx.createMediaElementSource(audioEl);
    const dest = audioCtx.createMediaStreamDestination();
    srcNode.connect(dest);
    srcNode.connect(audioCtx.destination);

    const canvasStream = canvas.captureStream(30);
    const mixedStream = new MediaStream([...canvasStream.getVideoTracks(), ...dest.stream.getAudioTracks()]);
    const preferredMime = ["video/mp4;codecs=h264,aac", "video/webm;codecs=vp9,opus", "video/webm"].find((m) => MediaRecorder.isTypeSupported(m)) || "video/webm";
    const recorder = new MediaRecorder(mixedStream, { mimeType: preferredMime, videoBitsPerSecond: 6_000_000 });
    const chunks = [];
    recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);

    function draw(t) {
      const s = scenes.find((sc) => t >= sc.start && t < sc.end) || scenes[scenes.length - 1];
      const im = imgCache[s.image];
      ctx.fillStyle = "#05070b";
      ctx.fillRect(0, 0, w, h);
      if (im && im.complete && im.naturalWidth) {
        const scale = Math.max(w / im.naturalWidth, h / im.naturalHeight);
        const iw = im.naturalWidth * scale;
        const ih = im.naturalHeight * scale;
        ctx.drawImage(im, (w - iw) / 2, (h - ih) / 2, iw, ih);
      }
      const capH = Math.round(h * 0.32);
      const grad = ctx.createLinearGradient(0, h - capH, 0, h);
      grad.addColorStop(0, "rgba(2,5,10,0)");
      grad.addColorStop(1, "rgba(2,5,10,0.92)");
      ctx.fillStyle = grad;
      ctx.fillRect(0, h - capH, w, capH);
      ctx.fillStyle = "#53e5ff";
      ctx.font = `bold ${Math.round(w * 0.032)}px system-ui, sans-serif`;
      ctx.fillText(s.speaker || "", w * 0.06, h - capH + Math.round(h * 0.05));
      ctx.fillStyle = "#fbfdff";
      ctx.font = `bold ${Math.round(w * 0.042)}px system-ui, sans-serif`;
      wrapText(ctx, s.dialogue || "", w * 0.06, h - capH + Math.round(h * 0.11), w * 0.88, Math.round(w * 0.052));
    }
    function wrapText(c, str, x, y, maxWidth, lineHeight) {
      let line = "";
      let yy = y;
      for (const ch of str) {
        const test = line + ch;
        if (c.measureText(test).width > maxWidth && line) {
          c.fillText(line, x, yy);
          line = ch;
          yy += lineHeight;
        } else line = test;
      }
      if (line) c.fillText(line, x, yy);
    }

    status.textContent = "録画中…";
    recorder.start();
    audioEl.currentTime = 0;
    await audioEl.play();
    await new Promise((resolve) => {
      function loop() {
        draw(audioEl.currentTime);
        bar.style.width = `${Math.min(100, (audioEl.currentTime / audioEl.duration) * 100)}%`;
        if (!audioEl.ended && !audioEl.paused) requestAnimationFrame(loop);
        else resolve();
      }
      loop();
      audioEl.onended = resolve;
    });
    recorder.stop();
    await new Promise((resolve) => {
      recorder.onstop = resolve;
    });
    const blob = new Blob(chunks, { type: preferredMime });
    const url = URL.createObjectURL(blob);
    const a = $("#videoDownload");
    a.href = url;
    a.download = `${state.epId}.${preferredMime.includes("mp4") ? "mp4" : "webm"}`;
    a.style.display = "inline-block";
    a.textContent = `ダウンロード (${(blob.size / 1024 / 1024).toFixed(1)}MB)`;
    status.textContent = "完了しました。";
  }

  // ---------- CSV import/export ----------
  function exportCSV() {
    const columns = ["speaker", "dialogue", "reading", "pause_ms", "cut"];
    const rows = state.lines.map((l) => ({ speaker: l.speaker, dialogue: l.text, reading: l.reading, pause_ms: l.pauseMs, cut: l.cut }));
    const csv = toCSV(rows, columns);
    downloadText(csv, `${state.epId}_dialogue.csv`);
  }
  function downloadText(text, filename) {
    const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  }
  function importCSV(text) {
    const rows = parseCSV(text);
    state.lines = rows.map((r, i) => ({
      id: `${state.epId}_v${String(i + 1).padStart(3, "0")}`,
      speaker: r.speaker || "",
      text: r.dialogue || "",
      reading: r.reading || r.dialogue || "",
      pauseMs: Number(r.pause_ms) || 400,
      cut: Math.min(CUT_COUNT, Math.max(1, Number(r.cut) || 1)),
      styleId: "",
      speakerName: "",
      generated: false,
    }));
    renderLines();
    renderAudioLines();
    log(`CSVから${state.lines.length}行を読み込みました。既存の行は置き換えられました。`);
  }

  // ---------- wiring ----------
  function setupTabs() {
    $$("nav.tabs button").forEach((btn) => {
      btn.addEventListener("click", () => {
        $$("nav.tabs button").forEach((b) => b.classList.remove("active"));
        $$("section.tab").forEach((s) => s.classList.remove("active"));
        btn.classList.add("active");
        $(`section.tab[data-tab="${btn.dataset.tab}"]`).classList.add("active");
        if (btn.dataset.tab === "images") renderCuts();
        if (btn.dataset.tab === "audio") renderAudioLines();
        if (btn.dataset.tab === "preview") renderPreview();
      });
    });
  }

  function setupSettings() {
    const c = ghConfig();
    $("#ghOwner").value = c.owner;
    $("#ghRepo").value = c.repo;
    $("#ghBranch").value = c.branch;
    $("#ghToken").value = c.token;
    $("#ghSave").addEventListener("click", async () => {
      localStorage.setItem("es_owner", $("#ghOwner").value.trim());
      localStorage.setItem("es_repo", $("#ghRepo").value.trim());
      localStorage.setItem("es_branch", $("#ghBranch").value.trim() || "gh-pages");
      localStorage.setItem("es_token", $("#ghToken").value.trim());
      const badge = $("#ghStatus");
      badge.textContent = "確認中…";
      badge.className = "badge warn";
      try {
        await ghCheckConnection();
        badge.textContent = "接続OK（書き込み可）";
        badge.className = "badge ok";
        log("GitHub接続を確認しました（書き込み権限あり）。");
      } catch (err) {
        badge.textContent = err.message.length > 60 ? "接続失敗（ログ参照）" : `接続失敗: ${err.message}`;
        badge.className = "badge bad";
        log(`GitHub接続に失敗: ${err.message}`);
      }
    });

    const epSelect = $("#episodeSelect");
    BUILTIN_EPISODES.forEach(([id, label]) => {
      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = label;
      epSelect.appendChild(opt);
    });
    epSelect.addEventListener("change", () => $("#loadEpisodeBtn").click());
    $("#loadEpisodeBtn").addEventListener("click", async () => {
      $("#episodeStatus").textContent = "読み込み中…";
      try {
        await loadEpisode(epSelect.value);
        renderLines();
        renderCuts();
        renderAudioLines();
        $("#episodeStatus").textContent = `${epSelect.value} を読み込みました。`;
      } catch (err) {
        $("#episodeStatus").textContent = `失敗: ${err.message}`;
      }
    });
    $("#newEpBtn").addEventListener("click", () => {
      const num = Number($("#newEpNum").value) || nextEpNum();
      const epId = `ep${String(num).padStart(2, "0")}`;
      const title = $("#newEpTitle").value || `第${num}話`;
      state.epId = epId;
      state.lines = [newLine(1, 1)];
      state.cuts = emptyCuts();
      const opt = document.createElement("option");
      opt.value = epId;
      opt.textContent = title;
      epSelect.appendChild(opt);
      epSelect.value = epId;
      renderLines();
      renderCuts();
      renderAudioLines();
      $("#episodeStatus").textContent = `${epId} を新規作成しました（まだ未保存）。セリフタブから編集してください。`;
    });

    $("#aivisCheck").addEventListener("click", async () => {
      const badge = $("#aivisStatus");
      badge.textContent = "確認中…";
      badge.className = "badge warn";
      try {
        const v = await aivisPing();
        badge.textContent = `接続OK (${v.version || "?"})`;
        badge.className = "badge ok";
      } catch (err) {
        badge.textContent = "未接続（PCでAivisSpeechを起動してください）";
        badge.className = "badge bad";
      }
    });
  }

  function setupDialogueTab() {
    $("#addLineBtn").addEventListener("click", () => {
      state.lines.push(newLine(state.lines.length + 1, state.lines[state.lines.length - 1]?.cut || 1));
      renderLines();
    });
    $("#saveDialogueBtn").addEventListener("click", async () => {
      const statusEl = $("#dialogueSaveStatus");
      const btn = $("#saveDialogueBtn");
      if (!state.epId) {
        statusEl.textContent = "❌ エピソードを先に読み込んでください（設定タブ）";
        return;
      }
      btn.disabled = true;
      statusEl.textContent = "保存中…";
      try {
        await saveDialogue();
        statusEl.textContent = "✅ 保存しました";
      } catch (err) {
        statusEl.textContent = `❌ 保存失敗: ${err.message}`;
        log(`保存失敗: ${err.message}`);
      } finally {
        btn.disabled = false;
      }
    });
    $("#csvExportBtn").addEventListener("click", exportCSV);
    $("#csvTemplateBtn").addEventListener("click", () => {
      downloadText(toCSV([{ speaker: "ナレーション", dialogue: "サンプルのセリフ。", reading: "サンプルのセリフ。", pause_ms: 400, cut: 1 }], ["speaker", "dialogue", "reading", "pause_ms", "cut"]), "dialogue_template.csv");
    });
    $("#csvImportBtn").addEventListener("click", async () => {
      const file = $("#csvFile").files[0];
      if (!file) {
        log("CSVファイルを選択してください。");
        return;
      }
      importCSV(await file.text());
    });
  }

  function setupImagesTab() {
    $("#saveCutsBtn").addEventListener("click", async () => {
      const btn = $("#saveCutsBtn");
      if (!state.epId) {
        log("エピソードを先に読み込んでください（設定タブ）");
        return;
      }
      btn.disabled = true;
      btn.textContent = "保存中…";
      try {
        await saveCuts();
        btn.textContent = "✅ カット情報をGitHubに保存";
      } catch (err) {
        btn.textContent = "❌ 保存失敗";
        log(`保存失敗: ${err.message}`);
      } finally {
        btn.disabled = false;
      }
    });
  }

  // ---------- cloud generation via GitHub Actions ----------
  const CLOUD_WORKFLOW = "generate-episode-audio.yml";

  async function cloudGenerate() {
    const st = $("#cloudGenStatus");
    const c = ghConfig();
    st.textContent = "セリフ・カット情報を保存中…";
    await saveDialogue();
    const files = epFiles(state.epId);
    await ghPutJSON(files.sceneManifest, buildSceneManifest(), `${state.epId} scene_manifest を更新（クラウド生成前）`);
    st.textContent = "GitHub Actions を起動中…";
    const res = await fetch(`https://api.github.com/repos/${c.owner}/${c.repo}/actions/workflows/${CLOUD_WORKFLOW}/dispatches`, {
      method: "POST",
      headers: { ...ghHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ ref: c.branch, inputs: { episode: state.epId } }),
    });
    if (res.status !== 204) {
      const t = await res.text();
      let msg = `起動失敗 → ${res.status} ${t.slice(0, 200)}`;
      if (res.status === 403 || res.status === 404) {
        msg += " ｜対処: PATの「Permissions→Actions」を Read and write にしてください";
      }
      throw new Error(msg);
    }
    // ポーリングで進行状況を表示
    const runsUrl = `https://api.github.com/repos/${c.owner}/${c.repo}/actions/workflows/${CLOUD_WORKFLOW}/runs?per_page=1`;
    const actionsPage = `https://github.com/${c.owner}/${c.repo}/actions`;
    await new Promise((r) => setTimeout(r, 5000));
    for (let i = 0; i < 120; i += 1) {
      let run = null;
      try {
        const rr = await fetch(runsUrl, { headers: ghHeaders() });
        if (rr.ok) run = (await rr.json()).workflow_runs?.[0] || null;
      } catch (e) { /* 一時的な失敗は無視して継続 */ }
      if (run) {
        if (run.status === "completed") {
          if (run.conclusion === "success") {
            st.innerHTML = `✅ 完了。1〜2分でPagesに反映されます（<a href="${run.html_url}" target="_blank" style="color:var(--cyan)">ログ</a>）`;
          } else {
            st.innerHTML = `❌ 失敗 (${run.conclusion})。<a href="${run.html_url}" target="_blank" style="color:var(--cyan)">ログを確認</a>`;
          }
          return;
        }
        st.innerHTML = `⏳ 実行中 (${run.status})… <a href="${run.html_url}" target="_blank" style="color:var(--cyan)">進行状況</a>`;
      } else {
        st.innerHTML = `⏳ 起動確認中… <a href="${actionsPage}" target="_blank" style="color:var(--cyan)">Actions</a>`;
      }
      await new Promise((r) => setTimeout(r, 15000));
    }
    st.innerHTML = `⏱ 監視を終了しました。<a href="${actionsPage}" target="_blank" style="color:var(--cyan)">Actionsページ</a>で確認してください`;
  }

  function setupAudioTab() {
    $("#cloudGenBtn").addEventListener("click", async () => {
      const btn = $("#cloudGenBtn");
      const st = $("#cloudGenStatus");
      if (!state.epId) {
        st.textContent = "❌ エピソードを先に読み込んでください（設定タブ）";
        return;
      }
      btn.disabled = true;
      try {
        await cloudGenerate();
      } catch (err) {
        st.textContent = `❌ ${err.message}`;
        log(`クラウド生成失敗: ${err.message}`);
      } finally {
        btn.disabled = false;
      }
    });
    $("#genAllBtn").addEventListener("click", () => generateAll(false));
    $("#genAllForceBtn").addEventListener("click", () => generateAll(true));
    $("#commitAudioBtn").addEventListener("click", async () => {
      const st = $("#commitStatus");
      const btn = $("#commitAudioBtn");
      btn.disabled = true;
      st.textContent = "結合・コミット中…";
      try {
        await commitAudio();
        st.textContent = "✅ コミット完了。プレビュー/紙芝居に反映されます";
      } catch (err) {
        st.textContent = `❌ ${err.message}`;
        log(`コミット失敗: ${err.message}`);
      } finally {
        btn.disabled = false;
      }
    });
  }

  function setupExportTab() {
    $("#publishPlayerBtn").addEventListener("click", publishPlayer);
    $("#renderVideoBtn").addEventListener("click", renderVideo);
  }

  function init() {
    setupTabs();
    setupSettings();
    setupDialogueTab();
    setupImagesTab();
    setupAudioTab();
    setupExportTab();
    state.epId = "ep01";
    state.cuts = emptyCuts();
    state.lines = [newLine(1, 1)];
    renderLines();
    log("Episode Studio 起動。設定タブでGitHub接続を行ってください。");
  }

  document.addEventListener("DOMContentLoaded", init);
})();
