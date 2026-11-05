/* Automata Lab frontend. No build step: plain JS + vis-network + Chart.js. */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

async function api(path, body) {
  const opts = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : undefined;
  const res = await fetch("/api" + path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    let msg = data.detail || "Request failed";
    if (Array.isArray(msg)) msg = msg.map((m) => m.msg).join("; ");
    throw new Error(msg);
  }
  return data;
}

function showError(id, msg) {
  const el = $(id);
  el.textContent = msg || "";
  el.hidden = !msg;
}

function setBtnLoading(btn, loading, defaultText) {
  if (!btn) return;
  if (loading) {
    if (!btn.dataset.origText) btn.dataset.origText = btn.textContent.trim();
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner" aria-hidden="true"></span>Running…`;
  } else {
    btn.disabled = false;
    btn.textContent = defaultText || btn.dataset.origText || "Submit";
  }
}

const pct = (x) => (x == null ? "n/a" : (x * 100).toFixed(1) + "%");
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const show = (s) => (s === "" ? "ε" : s);

const SUBSCRIPTS = { '0':'₀', '1':'₁', '2':'₂', '3':'₃', '4':'₄', '5':'₅', '6':'₆', '7':'₇', '8':'₈', '9':'₉' };
const toSubscript = (n) => String(n).split('').map((c) => SUBSCRIPTS[c] || c).join('');
const formatStateLabel = (label) => {
  const s = String(label);
  const m = s.match(/^([a-zA-Z]+)(\d+)$/);
  if (m) return `${m[1]}${toSubscript(m[2])}`;
  if (/^\d+$/.test(s)) return `q${toSubscript(s)}`;
  return s;
};

/* ------------------------------------------------------------------ *
 *  Graph drawing (vis-network with a custom renderer for double circles)
 * ------------------------------------------------------------------ */
const PAL = {
  idle:    { fill: "#FFFFFF", stroke: "#101820", text: "#101820" },
  visited: { fill: "#FBE7C6", stroke: "#E8890C", text: "#101820" },
  current: { fill: "#E8890C", stroke: "#E8890C", text: "#FFFFFF" },
  accept:  { fill: "#1A7F4B", stroke: "#1A7F4B", text: "#FFFFFF" },
  reject:  { fill: "#B3321F", stroke: "#B3321F", text: "#FFFFFF" },
};
const EDGE_IDLE = "#3A4550";
const EDGE_HOT = "#E8890C";

class Graph {
  constructor(el) {
    this.el = el;
    this.net = null;
    this.meta = {};
    this.edges = null;
    this.deadIds = new Set();
  }

  renderer(id, rawLabel) {
    const self = this;
    const label = formatStateLabel(rawLabel);
    return ({ ctx, x, y }) => {
      const r = 24;
      return {
        drawNode() {
          const m = self.meta[id] || {};
          const col = PAL[m.state || "idle"] || PAL.idle;
          ctx.save();
          if (m.start) {                       // start arrow drawn from the left
            ctx.strokeStyle = "#101820"; ctx.fillStyle = "#101820"; ctx.lineWidth = 1.6;
            ctx.beginPath(); ctx.moveTo(x - r - 28, y); ctx.lineTo(x - r - 2, y); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(x - r - 1, y); ctx.lineTo(x - r - 8, y - 4); ctx.lineTo(x - r - 8, y + 4); ctx.closePath(); ctx.fill();
          }
          if (m.dead) ctx.setLineDash([4, 3]);
          ctx.lineWidth = 1.6; ctx.strokeStyle = col.stroke; ctx.fillStyle = col.fill;
          ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
          if (m.acc) { ctx.beginPath(); ctx.arc(x, y, r - 5, 0, Math.PI * 2); ctx.stroke(); }
          ctx.setLineDash([]);
          ctx.fillStyle = col.text; ctx.font = "italic 600 15px 'Newsreader', serif";
          ctx.textAlign = "center"; ctx.textBaseline = "middle";
          ctx.fillText(label, x, y + 1);
          ctx.restore();
        },
        nodeDimensions: { width: r * 2, height: r * 2 },
      };
    };
  }

  load(g, showDead) {
    this.clearTimers();
    const allDead = g.nodes.every((n) => n.dead);
    this.deadIds = new Set(g.nodes.filter((n) => n.dead).map((n) => n.id));
    const hidden = (id) => this.deadIds.has(id) && !showDead && !allDead;
    this.meta = {};
    const nodes = g.nodes.filter((n) => !hidden(n.id)).map((n) => {
      this.meta[n.id] = { acc: n.accepting, start: n.start, dead: n.dead, state: "idle" };
      return { id: n.id, label: formatStateLabel(n.label), shape: "custom", size: 24, ctxRenderer: this.renderer(n.id, n.label) };
    });
    const edges = g.edges.filter((e) => !hidden(e.from) && !hidden(e.to)).map((e) => ({
      id: `${e.from}>${e.to}`, from: e.from, to: e.to, label: e.label, symbols: e.symbols,
      arrows: { to: { enabled: true, scaleFactor: 0.7 } },
      color: { color: EDGE_IDLE, highlight: EDGE_IDLE }, width: 1.4,
      font: { size: 16, face: "Newsreader", color: "#101820", strokeWidth: 5, strokeColor: "#F3F5F8", align: "horizontal" },
      smooth: e.from === e.to ? false : { enabled: true, type: "curvedCW", roundness: 0.22 },
    }));
    this.edges = new vis.DataSet(edges);
    const data = { nodes: new vis.DataSet(nodes), edges: this.edges };
    const options = {
      layout: { randomSeed: 11 },
      physics: {
        solver: "forceAtlas2Based",
        forceAtlas2Based: { gravitationalConstant: -110, springLength: 150, springConstant: 0.05, damping: 0.55 },
        stabilization: { iterations: 250 },
      },
      interaction: { dragNodes: true, hover: false, zoomView: true },
      nodes: { fixed: false },
    };
    if (this.net) this.net.destroy();
    this.net = new vis.Network(this.el, data, options);
    this.net.once("stabilizationIterationsDone", () => {
      this.net.setOptions({ physics: false });
      this.net.fit({ animation: false });
    });
  }

  resetColors() {
    Object.values(this.meta).forEach((m) => (m.state = "idle"));
    if (this.edges) this.edges.update(this.edges.getIds().map((id) => ({ id, color: { color: EDGE_IDLE, highlight: EDGE_IDLE }, width: 1.4 })));
    if (this.net) this.net.redraw();
  }

  /* nodeSeq: visited state ids in order; k: how many steps are shown;
     verdict: 'accept' | 'reject' | null (applied to the last node when k is final) */
  paintPath(nodeSeq, symSeq, k, verdict) {
    Object.values(this.meta).forEach((m) => (m.state = "idle"));
    for (let i = 0; i < k; i++) if (this.meta[nodeSeq[i]]) this.meta[nodeSeq[i]].state = "visited";
    const cur = this.meta[nodeSeq[k]];
    if (cur) cur.state = verdict && k === nodeSeq.length - 1 ? verdict : "current";
    const hot = new Set();
    for (let i = 0; i < k; i++) {
      const id = `${nodeSeq[i]}>${nodeSeq[i + 1]}`;
      if (this.edges && this.edges.get(id)) hot.add(id);
    }
    if (this.edges) {
      this.edges.update(this.edges.getIds().map((id) => ({
        id, color: { color: hot.has(id) ? EDGE_HOT : EDGE_IDLE, highlight: EDGE_HOT }, width: hot.has(id) ? 3 : 1.4,
      })));
    }
    if (this.net) this.net.redraw();
  }
    if (this.net) this.net.redraw();
  }

  clearTimers() { /* placeholder for symmetry with animation timers */ }
}

/* ------------------------------------------------------------------ *
 *  State
 * ------------------------------------------------------------------ */
const state = {
  languages: [],
  lang: null,          // preset key or "custom"
  refGraph: null,
  nfaGraph: null,
  learned: null,       // last /api/learn response
  view: "learned",
  steps: null, nodeSeq: null, symSeq: null, k: 0, accepted: null, playTimer: null,
  charts: {},
};
const mainGraph = new Graph($("#graphMain"));
const nfaGraph = new Graph($("#graphNfa"));
const nfaDfaGraph = new Graph($("#graphNfaDfa"));

/* ------------------------------------------------------------------ *
 *  Example parsing and formatting
 * ------------------------------------------------------------------ */
function parseLabel(tok) {
  const t = tok.toLowerCase();
  if (["+", "1", "accept", "yes", "true", "a", "✓", "acc"].includes(t)) return true;
  if (["-", "−", "–", "0", "reject", "no", "false", "r", "✗", "rej"].includes(t)) return false;
  return null;
}

function parseExamples(text, alphabet) {
  const rows = [], errors = [];
  text.split("\n").forEach((raw, i) => {
    const line = raw.trim();
    if (!line || line.startsWith("#")) return;
    const parts = line.split(/[\s,;:]+/).filter(Boolean);
    let s, lab;
    if (parts.length === 1) { s = ""; lab = parseLabel(parts[0]); }
    else { s = parts[0]; lab = parseLabel(parts[1]); }
    if (["ε", "eps", '""', "''", "λ"].includes(s.toLowerCase())) s = "";
    if (lab === null) { errors.push(`Line ${i + 1}: end the line with + or −.`); return; }
    const bad = [...s].find((c) => !alphabet.includes(c));
    if (bad) { errors.push(`Line ${i + 1}: "${bad}" is not in the alphabet (${alphabet.join(" ")}). Clear the alphabet field to detect it automatically.`); return; }
    rows.push({ s, label: lab });
  });
  return { rows, errors };
}

function formatExamples(rows) {
  return rows.map((r) => `${show(r.s)} ${r.label ? "+" : "−"}`).join("\n");
}

function inferAlphabet(text) {
  const syms = new Set();
  text.split("\n").forEach((raw) => {
    const line = raw.trim();
    if (!line || line.startsWith("#")) return;
    const parts = line.split(/[\s,;:]+/).filter(Boolean);
    const s = parts.length === 1 ? "" : parts[0];
    if (["ε", "eps", '""', "''", "λ"].includes(s.toLowerCase())) return;
    [...s].forEach((c) => syms.add(c));
  });
  return [...syms].sort();
}

function currentAlphabet() {
  if (state.lang && state.lang !== "custom") return state.languages.find((l) => l.key === state.lang).alphabet;
  const typed = [...new Set([...$("#alphabet").value.replace(/[\s,]/g, "")])];
  return typed.length ? typed : inferAlphabet($("#examples").value);
}

function updateSummary() {
  const alpha = currentAlphabet();
  const { rows, errors } = parseExamples($("#examples").value, alpha);
  const pos = rows.filter((r) => r.label).length;
  const alphaHint = alpha.length ? ` Alphabet: ${alpha.join(" ")}` : "";
  if (errors.length) {
    // If on a preset and symbols are outside that preset's alphabet, say so clearly
    if (state.lang && state.lang !== "custom") {
      const detected = inferAlphabet($("#examples").value);
      const presetAlpha = state.languages.find((l) => l.key === state.lang).alphabet;
      const outside = detected.filter((c) => !presetAlpha.includes(c));
      if (outside.length) {
        $("#exSummary").textContent = `These examples use symbols outside this preset's alphabet (${presetAlpha.join(" ")}). Switch the language to Custom.`;
        return;
      }
    }
    $("#exSummary").textContent = errors[0];
  } else {
    $("#exSummary").textContent = rows.length
      ? `${rows.length} examples: ${pos} accepted, ${rows.length - pos} rejected.${alphaHint}`
      : "No examples yet.";
  }
}

/* ------------------------------------------------------------------ *
 *  Language selection
 * ------------------------------------------------------------------ */
async function initLanguages() {
  state.languages = await api("/languages");
  const sel = $("#language");
  sel.innerHTML = state.languages.map((l) => `<option value="${l.key}">${esc(l.title)}</option>`).join("") +
    `<option value="custom">Custom (my own examples)</option>`;
  sel.addEventListener("change", () => onLanguage(sel.value, true));
  await onLanguage(state.languages[0].key, false);
}

async function onLanguage(key, clearExamples) {
  state.lang = key;
  const custom = key === "custom";
  $("#alphaField").hidden = !custom;
  if (custom) {
    $("#alphabet").value = "";   // clear any stale / browser-restored value
  }
  const refBtn = $('#viewSeg button[data-view="reference"]');
  if (refBtn) refBtn.hidden = custom;
  if (custom && state.view === "reference") {
    setView("learned");
  }
  const expBtn = $("#btnExp");
  if (expBtn) expBtn.disabled = custom;
  if (custom) {
    showError("#expError", "Experiments need a preset language as ground truth.");
  } else {
    showError("#expError", "");
  }
  const info = state.languages.find((l) => l.key === key);
  $("#langDesc").textContent = custom
    ? "Type your own alphabet and labeled strings. There is no reference to compare against."
    : `${info.desc} Smallest DFA: ${info.min_states} states (including the dead state).`;
  $("#algorithm option[value=lstar]", document).disabled = custom;
  if (custom && $("#algorithm").value === "lstar") $("#algorithm").value = "rpni";
  updateAlgoHint();
  state.refGraph = null; state.nfaGraph = null;
  $("#viewNfaBtn").hidden = custom || !info.has_nfa;
  if (!custom) {
    const ref = await api(`/reference/${key}`);
    state.refGraph = ref.graph;
    state.nfaGraph = ref.nfa;
  }
  if (clearExamples) {
    $("#examples").value = "";
    state.learned = null;
    setView("learned");
    resetOutputs();
  }
  updateSummary();
  if (!clearExamples) {   // first load: show something useful straight away
    await generate();
    await learn();
  }
}

function updateAlgoHint() {
  $("#algoHint").textContent = $("#algorithm").value === "lstar"
    ? "L* does not use the examples. It asks membership questions (is this string in the language?) and equivalence questions (is my guess right?), and the reference language answers."
    : "RPNI builds a tree from your examples, then merges states as long as no accepted and rejected string end up in the same state.";
}

/* ------------------------------------------------------------------ *
 *  Generate / learn
 * ------------------------------------------------------------------ */
async function generate() {
  if (state.lang === "custom") { showError("#learnError", "Pick a preset language to auto-generate examples, or type your own."); return; }
  showError("#learnError", "");
  const btn = $("#btnGenerate");
  setBtnLoading(btn, true);
  try {
    const r = await api("/generate", {
      language: state.lang,
      n: +$("#genN").value, max_len: +$("#genLen").value,
      noise: (+$("#genNoise").value || 0) / 100, balance: $("#genBalance").checked,
    });
    $("#examples").value = formatExamples(r.examples);
    updateSummary();
  } catch (e) { showError("#learnError", e.message); }
  finally { setBtnLoading(btn, false, "Generate examples"); }
}

function resetOutputs() {
  $("#verdict").hidden = true; $("#metrics").hidden = true; $("#runOut").hidden = true;
  $("#graphEmpty").hidden = false;
  if ($("#dfaTableWrap")) $("#dfaTableWrap").hidden = true;
  if ($("#figCaption")) $("#figCaption").textContent = "";
  if (mainGraph.net) { mainGraph.net.destroy(); mainGraph.net = null; }
  stopPlay();
}

async function learn() {
  showError("#learnError", "");
  const alphabet = currentAlphabet();
  if (!alphabet.length) { showError("#learnError", "Enter at least one alphabet symbol."); return; }
  const algorithm = $("#algorithm").value;
  const { rows, errors } = parseExamples($("#examples").value, alphabet);
  if (errors.length) { showError("#learnError", errors[0]); return; }
  if (algorithm === "rpni" && !rows.length) { showError("#learnError", "Add some labeled examples first."); return; }
  const maxLen = rows.length ? Math.max(1, ...rows.map((r) => r.s.length)) : +$("#genLen").value;
  const btn = $("#btnLearn");
  setBtnLoading(btn, true);
  try {
    const res = await api("/learn", {
      alphabet, examples: rows, algorithm,
      reference: state.lang === "custom" ? null : state.lang, test_max_len: maxLen,
    });
    state.learned = res;
    $("#graphEmpty").hidden = true;
    setView("learned");
    renderVerdict(res);
    renderMetrics(res);
    renderDfaTable();
    $("#runOut").hidden = true; stopPlay();
    $("#btnRun").textContent = "Run on learned DFA";
  } catch (e) { showError("#learnError", e.message); }
  finally { setBtnLoading(btn, false, "Learn automaton"); }
}

function renderVerdict(res) {
  const v = $("#verdict");
  v.hidden = false;
  if (!res.reference) {
    v.className = "verdict info";
    v.textContent = "Learned a DFA. Select a preset language to compare with a reference.";
    return;
  }
  if (res.reference.equivalent) {
    v.className = "verdict ok";
    v.innerHTML = `<strong>Same language as the reference.</strong> The learned machine accepts the exact language of the reference.`;
  } else {
    const ce = res.reference.counterexample;
    const refSays = res.reference.counterexample_ref_label ? "accepts" : "rejects";
    const youSay = res.reference.counterexample_ref_label ? "rejects" : "accepts";
    v.className = "verdict bad";
    v.innerHTML = `<span><strong>Different from the reference.</strong> Shortest disagreement: <code>${esc(show(ce))}</code>. The reference ${refSays} it; the learned DFA ${youSay} it.</span>
                   <button class="btn" id="btnTryCe">Test this string</button>`;
    $("#btnTryCe").addEventListener("click", () => { $("#testStr").value = ce; runTest(); });
  }
}

function renderMetrics(res) {
  const m = res.metrics, items = [];
  const refStates = res.reference ? res.reference.states : null;
  items.push(["States (learned)", `${res.states_minimized}`, refStates != null ? `reference ${refStates}` : "without dead state"]);
  if (res.algorithm === "rpni") {
    items.push(["Training accuracy", pct(res.train_accuracy), `${res.info.training_size} strings`]);
    items.push(["Tree size", `${res.info.pta_states}`, `${res.info.merges} merges`]);
  } else {
    items.push(["Membership queries", `${res.info.membership_queries}`, "questions asked"]);
    items.push(["Equivalence queries", `${res.info.equivalence_queries}`, "guesses checked"]);
  }
  if (m) {
    items.push(["Accuracy on unseen strings", pct(m.accuracy), `${m.tested} tested`]);
    items.push(["F1 score", m.f1.toFixed(3), `P ${m.precision.toFixed(2)} · R ${m.recall.toFixed(2)}`]);
    items.push(["Shorter strings", pct(m.acc_short), "within training length"]);
    items.push(["Longer strings", pct(m.acc_long), "up to 2× training length"]);
    items.push(["Mistakes", `${m.false_accepts + m.false_rejects}`, `${m.false_accepts} false accept, ${m.false_rejects} false reject`]);
  }
  items.push(["Learning time", `${res.time_ms}`, "ms"]);
  const el = $("#metrics");
  el.hidden = false;
  el.innerHTML = items.map(([k, v, s]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}<small>${esc(s)}</small></dd></div>`).join("");
}

function updateFigCaption() {
  const el = $("#figCaption");
  if (!el) return;
  let g = null, name = "";
  if (state.view === "learned") {
    g = state.learned && state.learned.graph;
    name = "Learned DFA";
  } else if (state.view === "reference") {
    g = state.refGraph;
    name = "Reference DFA";
  } else if (state.view === "nfa") {
    g = state.nfaGraph;
    name = "Reference NFA";
  }
  if (!g || !g.nodes || !g.nodes.length) {
    el.textContent = "";
    return;
  }
  const total = g.nodes.length;
  const acc = g.nodes.filter((n) => n.accepting).length;
  el.textContent = `Figure 1. ${name}: ${total} state${total === 1 ? "" : "s"}, ${acc} accepting.`;
}

function renderDfaTable() {
  const wrap = $("#dfaTableWrap");
  if (!state.learned || !state.learned.dfa) {
    if (wrap) wrap.hidden = true;
    return;
  }
  const dfa = state.learned.dfa;
  const transMap = new Map();
  (dfa.transitions || []).forEach(([from, sym, to]) => {
    transMap.set(`${from}:${sym}`, to);
  });
  const alphabet = dfa.alphabet || [];
  const states = dfa.states || [];
  const acceptingSet = new Set(dfa.accepting || []);

  let html = `<thead><tr><th>State (δ)</th>${alphabet.map((a) => `<th>on <code>${esc(a)}</code></th>`).join("")}</tr></thead><tbody>`;

  states.forEach((s) => {
    const isStart = s === dfa.start;
    const isAcc = acceptingSet.has(s);
    let marker = "";
    if (isStart && isAcc) marker = "→ *";
    else if (isStart) marker = "→";
    else if (isAcc) marker = "*";

    html += `<tr data-state="${s}">`;
    html += `<td class="mono font-semibold">${marker ? `<span class="marker">${marker}</span> ` : `<span class="marker"></span>`}q${toSubscript(s)}</td>`;
    alphabet.forEach((a) => {
      const to = transMap.get(`${s}:${a}`);
      const toStr = to !== undefined ? `q${toSubscript(to)}` : "–";
      html += `<td class="mono">${toStr}</td>`;
    });
    html += `</tr>`;
  });

  html += `</tbody>`;
  const table = $("#dfaTable");
  if (table) table.innerHTML = html;
  if (wrap) wrap.hidden = false;
}

/* ------------------------------------------------------------------ *
 *  Graph view switching
 * ------------------------------------------------------------------ */
function setView(v) {
  state.view = v;
  $$("#viewSeg button").forEach((b) => b.classList.toggle("on", b.dataset.view === v));
  drawMain();
}

function drawMain() {
  const showDead = $("#showDead").checked;
  let g = null;
  if (state.view === "learned") g = state.learned && state.learned.graph;
  if (state.view === "reference") g = state.refGraph;
  if (state.view === "nfa") g = state.nfaGraph;
  if (!g) {
    if (mainGraph.net) { mainGraph.net.destroy(); mainGraph.net = null; }
    $("#graphEmpty").hidden = false;
    $("#graphEmpty").textContent = state.view === "learned"
      ? "Provide examples and select Learn automaton to display the machine."
      : "No reference machine for a custom language.";
    updateFigCaption();
    return;
  }
  $("#graphEmpty").hidden = true;
  mainGraph.load(g, showDead);
  updateFigCaption();
}

/* ------------------------------------------------------------------ *
 *  Test a string, step by step
 * ------------------------------------------------------------------ */
function stopPlay() {
  if (state.playTimer) { clearInterval(state.playTimer); state.playTimer = null; }
  $("#stepPlay").textContent = "Play";
}

async function runTest() {
  showError("#runError", "");
  if (!state.learned) { showError("#runError", "Learn an automaton first."); return; }
  const s = $("#testStr").value.replace(/ε/g, "").trim();
  stopPlay();
  const btn = $("#btnRun");
  setBtnLoading(btn, true);
  try {
    const r = await api("/run", {
      kind: "dfa", automaton: state.learned.dfa, string: s,
      reference: state.lang === "custom" ? null : state.lang,
    });
    state.steps = r.steps; state.accepted = r.accepted;
    state.nodeSeq = [r.start, ...r.steps.map((st) => st.to)];
    state.symSeq = r.steps.map((st) => st.sym);
    state.ref = r;
    // the path may cross the dead state: reveal it so the walk is visible
    if (state.view !== "learned") setView("learned");
    if (state.nodeSeq.some((id) => !mainGraph.meta[id])) { $("#showDead").checked = true; drawMain(); }
    state.k = 0;
    $("#runOut").hidden = false;
    paintStep();
  } catch (e) { showError("#runError", e.message); }
  finally { setBtnLoading(btn, false, "Run on learned DFA"); }
}

function paintStep() {
  const n = state.nodeSeq.length - 1;
  const final = state.k === n;
  const verdict = final ? (state.accepted ? "accept" : "reject") : null;
  mainGraph.paintPath(state.nodeSeq, state.symSeq, state.k, verdict);
  const parts = [];
  state.nodeSeq.forEach((id, i) => {
    let cls = "st";
    if (i < state.k) cls += " done";
    else if (i === state.k) cls += final ? (state.accepted ? " accept" : " reject") : " now";
    else cls += " ahead";
    if (i > 0) parts.push(`<span class="sym ${i > state.k ? "ahead" : ""}">–${esc(state.symSeq[i - 1])}→</span>`);
    parts.push(`<span class="${cls}">q${toSubscript(id)}</span>`);
  });
  $("#trace").innerHTML = parts.join("");
  const res = $("#runResult");
  if (final) {
    let t = state.accepted ? `<b class="acc">Accepted</b>` : `<b class="rej">Rejected</b>`;
    if (state.ref && state.ref.reference_accepts !== undefined) {
      t += state.ref.agrees ? ` · agrees with the reference` : ` · <b class="rej">reference says ${state.ref.reference_accepts ? "accept" : "reject"}</b>`;
    }
    res.innerHTML = t;
  } else {
    res.textContent = `Step ${state.k} of ${n}`;
  }
  $("#stepBack").disabled = state.k === 0;
  $("#stepNext").disabled = final;

  // Highlight current state in the transition table
  const curStateId = state.nodeSeq[state.k];
  $$("#dfaTable tr[data-state]").forEach((row) => {
    row.classList.toggle("current-row", row.dataset.state == curStateId);
  });
}

function step(d) {
  const n = state.nodeSeq.length - 1;
  state.k = Math.max(0, Math.min(n, state.k + d));
  paintStep();
}

function togglePlay() {
  if (state.playTimer) { stopPlay(); return; }
  if (state.k >= state.nodeSeq.length - 1) state.k = 0;
  $("#stepPlay").textContent = "Pause";
  paintStep();
  state.playTimer = setInterval(() => {
    if (state.k >= state.nodeSeq.length - 1) { stopPlay(); return; }
    step(1);
    if (state.k >= state.nodeSeq.length - 1) stopPlay();
  }, 650);
}

/* ------------------------------------------------------------------ *
 *  Experiments
 * ------------------------------------------------------------------ */
function lineChart(id, labels, accuracy, states, refStates, xTitle) {
  if (state.charts[id]) state.charts[id].destroy();
  const mono = { family: "'IBM Plex Mono', monospace", size: 11 };
  state.charts[id] = new Chart($("#" + id), {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Accuracy on unseen strings", data: accuracy, yAxisID: "y", borderColor: "#1F3FBF", backgroundColor: "#1F3FBF", tension: 0.2, pointRadius: 3.5 },
        { label: "States learned", data: states, yAxisID: "y2", borderColor: "#E8890C", backgroundColor: "#E8890C", tension: 0.2, pointRadius: 3.5 },
        { label: "States in reference", data: labels.map(() => refStates), yAxisID: "y2", borderColor: "#101820", borderDash: [5, 4], pointRadius: 0, borderWidth: 1.4 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { position: "bottom", labels: { boxWidth: 14, font: { size: 12, family: "'IBM Plex Sans', sans-serif" } } } },
      scales: {
        x: { title: { display: true, text: xTitle, font: { family: "'IBM Plex Sans', sans-serif" } }, ticks: { font: mono } },
        y: { min: 0.4, max: 1, title: { display: true, text: "Accuracy", font: { family: "'IBM Plex Sans', sans-serif" } }, ticks: { callback: (v) => Math.round(v * 100) + "%", font: mono } },
        y2: { position: "right", min: 0, title: { display: true, text: "States", font: { family: "'IBM Plex Sans', sans-serif" } }, grid: { drawOnChartArea: false }, ticks: { font: mono, precision: 0 } },
      },
    },
  });
}

async function runExperiment() {
  showError("#expError", "");
  if (state.lang === "custom") { showError("#expError", "Experiments need a preset language as ground truth."); return; }
  const btn = $("#btnExp");
  setBtnLoading(btn, true);
  try {
    const r = await api("/experiment", {
      language: state.lang, trials: +$("#expTrials").value, noise_size: +$("#expNoiseN").value,
      max_len: +$("#genLen").value,
    });
    const sc = r.size_curve, nc = r.noise_curve;
    if ($("#emptySize")) $("#emptySize").hidden = true;
    if ($("#chartSize")) $("#chartSize").hidden = false;
    if ($("#emptyNoise")) $("#emptyNoise").hidden = true;
    if ($("#chartNoise")) $("#chartNoise").hidden = false;
    lineChart("chartSize", sc.map((p) => p.x), sc.map((p) => p.accuracy), sc.map((p) => p.states), r.ref_states, "Training examples");
    lineChart("chartNoise", nc.map((p) => Math.round(p.x * 100) + "%"), nc.map((p) => p.accuracy), nc.map((p) => p.states), r.ref_states, `Labels flipped (${r.noise_size} examples)`);
    const firstExact = sc.find((p) => p.exact_rate >= 0.8);
    $("#noteSize").textContent = firstExact
      ? `The exact reference language was recovered in at least 80% of trials from ${firstExact.x} examples.`
      : "The exact reference language was not recovered reliably in this range. Try more examples or longer strings.";
    const clean = nc[0], worst = nc[nc.length - 1];
    $("#noteNoise").textContent =
      `With clean labels the learner averages ${clean.states.toFixed(1)} states; at ${Math.round(worst.x * 100)}% noise it averages ${worst.states.toFixed(1)} and accuracy drops to ${pct(worst.accuracy)}. RPNI must fit every label, so noise forces extra states.`;
  } catch (e) { showError("#expError", e.message); }
  finally { setBtnLoading(btn, false, "Run experiment"); }
}

/* ------------------------------------------------------------------ *
 *  Clusters
 * ------------------------------------------------------------------ */
async function runCluster() {
  showError("#clusterError", "");
  const alphabet = currentAlphabet();
  const { rows, errors } = parseExamples($("#examples").value, alphabet);
  if (errors.length) { showError("#clusterError", errors[0]); return; }
  const btn = $("#btnCluster");
  setBtnLoading(btn, true);
  try {
    const r = await api("/cluster", { alphabet, examples: rows, k: +$("#clusterK").value });
    const colors = ["#1F3FBF", "#E8890C", "#1A7F4B", "#B3321F", "#5C6773", "#6F42C1", "#8C6843", "#007A87"];
    const sets = [];
    const k = +$("#clusterK").value;
    for (let c = 0; c < k; c++) {
      [true, false].forEach((lab) => {
        const pts = r.points.filter((p) => p.cluster === c && p.label === lab);
        if (!pts.length) return;
        sets.push({
          label: `Cluster ${c + 1}, ${lab ? "accepted" : "rejected"}`,
          data: pts.map((p) => ({ x: p.x, y: p.y, s: p.s })),
          pointStyle: lab ? "circle" : "triangle", pointRadius: 5.5,
          backgroundColor: colors[c % colors.length] + (lab ? "" : "99"), borderColor: colors[c % colors.length],
        });
      });
    }
    if (state.charts.cluster) state.charts.cluster.destroy();
    if ($("#emptyCluster")) $("#emptyCluster").hidden = true;
    if ($("#chartCluster")) $("#chartCluster").hidden = false;
    state.charts.cluster = new Chart($("#chartCluster"), {
      type: "scatter", data: { datasets: sets },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { position: "bottom", labels: { boxWidth: 12, font: { size: 11.5, family: "'IBM Plex Sans', sans-serif" } } },
          tooltip: { callbacks: { label: (ctx) => `"${show(ctx.raw.s)}"` } },
        },
        scales: {
          x: { title: { display: true, text: "Principal component 1", font: { family: "'IBM Plex Sans', sans-serif" } }, ticks: { font: { family: "'IBM Plex Mono', monospace" } } },
          y: { title: { display: true, text: "Principal component 2", font: { family: "'IBM Plex Sans', sans-serif" } }, ticks: { font: { family: "'IBM Plex Mono', monospace" } } }
        },
      },
    });
    const t = $("#clusterTable");
    t.hidden = false;
    t.innerHTML = `<tr><th>Cluster</th><th>Strings</th><th>Accepted</th><th>Rejected</th><th>Avg length</th></tr>` +
      r.summary.map((s) => `<tr><td>${s.cluster + 1}</td><td class="mono">${s.size}</td><td class="mono">${s.accepted}</td><td class="mono">${s.rejected}</td><td class="mono">${s.avg_len.toFixed(1)}</td></tr>`).join("");
  } catch (e) { showError("#clusterError", e.message); }
  finally { setBtnLoading(btn, false, "Cluster current examples"); }
}

/* ------------------------------------------------------------------ *
 *  NFA to DFA
 * ------------------------------------------------------------------ */
const NFA_DEFAULT = `alphabet: 0 1
start: 0
accept: 3
# one transition per line:  state symbol -> targets
0 0 -> 0
0 1 -> 0,1
1 0 -> 2
1 1 -> 2
2 0 -> 3
2 1 -> 3`;

function parseNfa(text) {
  const out = { alphabet: [], start: 0, accepting: [], transitions: [] };
  const num = (t) => { const n = parseInt(String(t).replace(/^q/i, ""), 10); if (Number.isNaN(n)) throw new Error(`"${t}" is not a state number`); return n; };
  text.split("\n").forEach((raw) => {
    const line = raw.trim();
    if (!line || line.startsWith("#")) return;
    let m;
    if ((m = line.match(/^alphabet\s*:\s*(.+)$/i))) out.alphabet = m[1].split(/[\s,]+/).filter(Boolean);
    else if ((m = line.match(/^start\s*:\s*(.+)$/i))) out.start = num(m[1].trim());
    else if ((m = line.match(/^accept(?:ing)?\s*:\s*(.+)$/i))) out.accepting = m[1].split(/[\s,]+/).filter(Boolean).map(num);
    else if ((m = line.match(/^(\S+)\s+(\S+)\s*(?:->|→)\s*(.+)$/))) {
      out.transitions.push([num(m[1]), m[2], m[3].split(/[\s,]+/).filter(Boolean).map(num)]);
    } else throw new Error(`Cannot read line: "${line}"`);
  });
  if (!out.alphabet.length) throw new Error("Add a line like  alphabet: 0 1");
  return out;
}

async function runNfa() {
  showError("#nfaError", "");
  const btn = $("#btnNfa");
  setBtnLoading(btn, true);
  try {
    const nfa = parseNfa($("#nfaText").value);
    nfa.test_strings = $("#nfaTests").value.split(",").map((s) => s.trim()).filter((s) => s.length).map((s) => (s === "ε" ? "" : s));
    const r = await api("/nfa/convert", nfa);
    nfaGraph.load(r.nfa_graph, true);
    nfaDfaGraph.load(r.min_graph, false);
    const capNfa = $("#figNfaCaption");
    if (capNfa) capNfa.textContent = `Figure 2. NFA: ${r.nfa_states} states, ${r.nfa.accepting ? r.nfa.accepting.length : 0} accepting.`;
    const capDfa = $("#figNfaDfaCaption");
    if (capDfa) capDfa.textContent = `Figure 3. Equivalent minimal DFA: ${r.min_states} states.`;
    $("#nfaSummary").textContent = `${r.nfa_states} NFA states became ${r.dfa_states} DFA states after subset construction, and ${r.min_states} after minimization.`;
    const st = $("#subsetTable");
    st.hidden = false;
    st.innerHTML = `<tr><th>DFA state</th><th>NFA states it stands for</th>${nfa.alphabet.map((a) => `<th>on ${esc(a)}</th>`).join("")}<th>Accepting</th></tr>` +
      r.table.map((row) => `<tr><td class="mono">d${row.id}</td><td class="mono">${esc(row.subset_label)}</td>${nfa.alphabet.map((a) => `<td class="mono">d${row.moves[a]}</td>`).join("")}<td>${row.accepting ? "yes" : "no"}</td></tr>`).join("");
    const tt = $("#nfaTestTable");
    tt.hidden = !r.tests.length;
    tt.innerHTML = `<tr><th>String</th><th>NFA</th><th>Minimal DFA</th></tr>` +
      r.tests.map((t) => `<tr><td class="mono">${esc(show(t.s))}</td><td class="${t.nfa ? "yes" : "no"}">${t.nfa ? "accepts" : "rejects"}</td><td class="${t.dfa ? "yes" : "no"}">${t.dfa ? "accepts" : "rejects"}</td></tr>`).join("");
  } catch (e) { showError("#nfaError", e.message); }
  finally { setBtnLoading(btn, false, "Convert to DFA"); }
}

let relayoutTimer = null;
function relayoutGraph() {
  if (!mainGraph.net) return;
  if (relayoutTimer) clearTimeout(relayoutTimer);
  mainGraph.net.setOptions({ physics: true });
  relayoutTimer = setTimeout(() => {
    if (mainGraph.net) {
      mainGraph.net.setOptions({ physics: false });
      mainGraph.net.fit({ animation: true });
    }
  }, 2000);
}

function fitGraph() {
  if (mainGraph.net) mainGraph.net.fit({ animation: true });
}

function saveGraphPng() {
  const canvas = $("#graphMain canvas");
  if (!canvas) return;
  const off = document.createElement("canvas");
  off.width = canvas.width;
  off.height = canvas.height;
  const ctx = off.getContext("2d");
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, off.width, off.height);
  ctx.drawImage(canvas, 0, 0);

  const a = document.createElement("a");
  a.href = off.toDataURL("image/png");
  a.download = (state.view || "dfa") + ".png";
  a.click();
}

function downloadDfaJson() {
  if (!state.learned || !state.learned.dfa) return;
  const blob = new Blob([JSON.stringify(state.learned.dfa, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = (state.lang && state.lang !== "custom" ? state.lang : "learned") + "_dfa.json";
  a.click();
  URL.revokeObjectURL(url);
}

/* ------------------------------------------------------------------ *
 *  Wiring
 * ------------------------------------------------------------------ */
$$(".tab").forEach((t) => t.addEventListener("click", () => {
  $$(".tab").forEach((x) => x.classList.toggle("active", x === t));
  $$(".panel").forEach((p) => p.classList.toggle("active", p.id === "tab-" + t.dataset.tab));
  if (t.dataset.tab === "nfa" && !nfaGraph.net) runNfa();
  if (t.dataset.tab === "learn" && mainGraph.net) setTimeout(() => mainGraph.net.fit(), 30);
}));
$$("#viewSeg button").forEach((b) => b.addEventListener("click", () => setView(b.dataset.view)));
$("#showDead").addEventListener("change", drawMain);
$("#btnRelayout").addEventListener("click", relayoutGraph);
$("#btnFit").addEventListener("click", fitGraph);
$("#btnSavePng").addEventListener("click", saveGraphPng);
$("#btnDlJson").addEventListener("click", downloadDfaJson);
$("#btnGenerate").addEventListener("click", generate);
$("#btnLearn").addEventListener("click", learn);
$("#algorithm").addEventListener("change", updateAlgoHint);
$("#examples").addEventListener("input", updateSummary);
$("#alphabet").addEventListener("input", updateSummary);
$("#btnRun").addEventListener("click", runTest);
$("#testStr").addEventListener("keydown", (e) => { if (e.key === "Enter") runTest(); });
$("#stepBack").addEventListener("click", () => { stopPlay(); step(-1); });
$("#stepNext").addEventListener("click", () => { stopPlay(); step(1); });
$("#stepPlay").addEventListener("click", togglePlay);
$("#btnExp").addEventListener("click", runExperiment);
$("#btnCluster").addEventListener("click", runCluster);
$("#btnNfa").addEventListener("click", runNfa);
$("#nfaText").value = NFA_DEFAULT;

initLanguages().catch((e) => showError("#learnError", "Could not reach the server: " + e.message));
