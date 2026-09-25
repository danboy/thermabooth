"use strict";

const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const FILTER_LABELS = { none: "Original", bw: "B&W", noir: "Noir", sepia: "Sepia", vivid: "Vivid", warm: "Warm", cool: "Cool", vintage: "Vintage" };
const FRAME_COLORS = { white: "#ffffff", black: "#141414", cream: "#faf4e4", pink: "#ffd6e0", sky: "#d0e6fa" };
const IDLE_MS = 120000;

const state = { cfg: null, sid: null, settings: { filter: "none", layout: "grid", frame: "white", caption: "" } };
let idleTimer = null;
let renderSeq = 0;

// ---------- helpers ----------
async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch (_) { /* keep statusText */ }
    throw new Error(msg);
  }
  return res.json();
}

function toast(msg, ok = false) {
  const t = $("toast");
  t.textContent = msg;
  t.className = ok ? "ok" : "";
  clearTimeout(toast.t);
  toast.t = setTimeout(() => t.classList.add("hidden"), 4000);
}

function show(name) {
  for (const s of document.querySelectorAll(".screen")) s.classList.toggle("hidden", s.id !== name);
  const live = $("live");
  if (name === "attract" || name === "shoot") {
    if (!live.getAttribute("src")) live.src = "/stream";
  } else {
    live.removeAttribute("src"); // stop pulling MJPEG while editing
  }
  bumpIdle(name);
}

function bumpIdle(name = currentScreen()) {
  clearTimeout(idleTimer);
  if (name === "edit" || name === "share") idleTimer = setTimeout(reset, IDLE_MS);
}
const currentScreen = () => (document.querySelector(".screen:not(.hidden)") || {}).id;
document.addEventListener("pointerdown", () => bumpIdle());

function reset() {
  state.sid = null;
  state.settings = { filter: "none", layout: "grid", frame: "white", caption: "" };
  $("print-status").textContent = "";
  $("modal").classList.add("hidden");
  $("qr-modal").classList.add("hidden");
  show("attract");
}

// ---------- shooting ----------
function buildThumbs(n) {
  const box = $("thumbs");
  box.replaceChildren();
  for (let i = 0; i < n; i++) box.append(document.createElement("div"));
}

async function shoot(slots) {
  show("shoot");
  const n = state.cfg.photos;
  if (slots.length === n) buildThumbs(n);
  else if (!$("thumbs").children.length) buildThumbs(n);
  try {
    for (const slot of slots) {
      const thumb = $("thumbs").children[slot];
      for (const el of $("thumbs").children) el.classList.remove("active");
      thumb.classList.add("active");
      $("shoot-info").textContent = slots.length === n ? `Photo ${slot + 1} of ${n}` : "Retake!";
      for (let c = state.cfg.countdown; c > 0; c--) {
        $("count").textContent = c;
        await sleep(1000);
      }
      $("count").textContent = "";
      $("flash").classList.add("on");
      const capture = api("POST", `/api/session/${state.sid}/capture`, { slot });
      await sleep(60);
      $("flash").classList.remove("on");
      await capture;
      thumb.style.backgroundImage = `url(/api/session/${state.sid}/photo/${slot}?t=${Date.now()})`;
      await sleep(900);
    }
  } catch (e) {
    toast(`Camera problem: ${e.message}`);
    $("count").textContent = "";
    show("attract");
    return;
  }
  await openEdit();
}

async function startSession() {
  try {
    state.sid = (await api("POST", "/api/session")).id;
  } catch (e) {
    toast(`Couldn't start: ${e.message}`);
    return;
  }
  state.settings = { filter: "none", layout: "grid", frame: "white", caption: "" };
  await shoot([...Array(state.cfg.photos).keys()]);
}

// ---------- edit ----------
function buildEditControls() {
  const filters = $("filters");
  filters.replaceChildren();
  for (const f of state.cfg.filters) {
    const b = document.createElement("button");
    b.className = "chip";
    b.dataset.filter = f;
    const img = document.createElement("img");
    img.alt = "";
    img.dataset.name = f;
    const label = document.createElement("div");
    label.textContent = FILTER_LABELS[f] || f;
    b.append(img, label);
    b.onclick = () => setSetting({ filter: f });
    filters.append(b);
  }
  const frames = $("frames");
  frames.replaceChildren();
  for (const f of state.cfg.frames) {
    const b = document.createElement("button");
    b.className = "dot";
    b.dataset.frame = f;
    b.style.background = FRAME_COLORS[f] || f;
    b.setAttribute("aria-label", f);
    b.onclick = () => setSetting({ frame: f });
    frames.append(b);
  }
  for (const b of document.querySelectorAll("[data-layout]")) b.onclick = () => setSetting({ layout: b.dataset.layout });
}

function refreshSelection() {
  const s = state.settings;
  for (const b of document.querySelectorAll("[data-filter]")) b.classList.toggle("sel", b.dataset.filter === s.filter);
  for (const b of document.querySelectorAll("[data-frame]")) b.classList.toggle("sel", b.dataset.frame === s.frame);
  for (const b of document.querySelectorAll("[data-layout]")) b.classList.toggle("sel", b.dataset.layout === s.layout);
  $("caption-btn").textContent = s.caption ? `“${s.caption}”` : "Add a caption";
}

async function rerender() {
  const seq = ++renderSeq;
  $("busy").classList.remove("hidden");
  try {
    await api("POST", `/api/session/${state.sid}/render`, state.settings);
    if (seq !== renderSeq) return;
    $("result").src = `/api/session/${state.sid}/final.jpg?t=${Date.now()}`;
  } catch (e) {
    toast(e.message);
  } finally {
    if (seq === renderSeq) $("busy").classList.add("hidden");
  }
}

function setSetting(patch) {
  Object.assign(state.settings, patch);
  refreshSelection();
  rerender();
}

async function openEdit() {
  show("edit");
  refreshSelection();
  for (const img of document.querySelectorAll("#filters img")) img.src = `/api/session/${state.sid}/filter-thumb/${img.dataset.name}?t=${Date.now()}`;
  const rt = $("retake");
  rt.replaceChildren();
  for (let i = 0; i < state.cfg.photos; i++) {
    const b = document.createElement("button");
    b.className = "rt";
    b.style.backgroundImage = `url(/api/session/${state.sid}/photo/${i}?t=${Date.now()})`;
    b.setAttribute("aria-label", `Retake photo ${i + 1}`);
    b.onclick = () => shoot([i]);
    rt.append(b);
  }
  await rerender();
}

// ---------- on-screen keyboard modal ----------
let kb = null;

function askText({ title, mode, initial = "", max = 60 }) {
  return new Promise((resolve) => {
    kb = { value: initial, shift: false, mode, max, resolve };
    $("modal-title").textContent = title;
    $("modal").classList.remove("hidden");
    renderKeyboard();
  });
}

function closeModal(result) {
  $("modal").classList.add("hidden");
  const r = kb && kb.resolve;
  kb = null;
  if (r) r(result);
}

function renderKeyboard() {
  const input = $("modal-input");
  input.textContent = kb.value || (kb.mode === "phone" ? "Phone number" : kb.mode === "email" ? "you@example.com" : "Type here");
  input.classList.toggle("empty", !kb.value);
  const box = $("keyboard");
  box.replaceChildren();
  const addRow = (keys) => {
    const row = document.createElement("div");
    row.className = "krow";
    for (const k of keys) row.append(k);
    box.append(row);
  };
  const key = (label, fn, cls = "") => {
    const b = document.createElement("button");
    b.className = `key ${cls}`;
    b.textContent = label;
    b.onclick = () => { fn(); renderKeyboard(); };
    return b;
  };
  const type = (ch) => () => { if (kb.value.length < kb.max) kb.value += kb.shift ? ch.toUpperCase() : ch; kb.shift = false; };
  const back = key("⌫", () => { kb.value = kb.value.slice(0, -1); }, "wide");

  if (kb.mode === "phone") {
    for (const r of ["123", "456", "789"]) addRow([...r].map((c) => key(c, type(c))));
    addRow([key("+", type("+")), key("0", type("0")), back]);
    return;
  }
  const rows = ["1234567890", "qwertyuiop", "asdfghjkl", "zxcvbnm"];
  const letter = (c) => key(kb.shift ? c.toUpperCase() : c, type(c));
  addRow([...rows[0]].map((c) => key(c, type(c))));
  addRow([...rows[1]].map(letter));
  addRow([...rows[2]].map(letter));
  addRow([key("⇧", () => { kb.shift = !kb.shift; }, `wide ${kb.shift ? "on" : ""}`), ...[...rows[3]].map(letter), back]);
  const extras = kb.mode === "email"
    ? [key("@", type("@")), key(".", type(".")), key("-", type("-")), key("_", type("_")), key(".com", () => { kb.value += ".com"; }, "wide")]
    : [key("!", type("!")), key("?", type("?")), key(".", type(".")), key(",", type(","))];
  addRow([...extras, key("space", type(" "), "space")]);
}

$("modal-ok").onclick = () => closeModal(kb ? kb.value.trim() : null);
$("modal-cancel").onclick = () => closeModal(null);

// ---------- share ----------
async function sendTo(kind) {
  const isEmail = kind === "email";
  const to = await askText({
    title: isEmail ? "Where should we send them?" : "Your phone number",
    mode: isEmail ? "email" : "phone",
    max: 80,
  });
  if (!to) return;
  const btn = $(isEmail ? "btn-email" : "btn-sms");
  btn.disabled = true;
  try {
    await api("POST", `/api/session/${state.sid}/${kind}`, { to });
    toast(isEmail ? "Sent! Check your inbox." : "Sent! Check your messages.", true);
  } catch (e) {
    toast(e.message);
  } finally {
    btn.disabled = false;
  }
}

async function doPrint() {
  const out = $("print-status");
  try {
    await api("POST", `/api/session/${state.sid}/print`);
  } catch (e) {
    out.textContent = e.message;
    return;
  }
  $("btn-print").disabled = true;
  for (;;) {
    await sleep(1000);
    let s;
    try { s = await api("GET", "/api/print/status"); } catch (_) { continue; }
    out.textContent = s.message;
    if (s.state === "done" || s.state === "error" || s.state === "idle") break;
  }
  $("btn-print").disabled = false;
}

async function showQr() {
  $("qr").src = `/api/session/${state.sid}/qr.svg?t=${Date.now()}`;
  $("qr-modal").classList.remove("hidden");
}

// ---------- init ----------
async function init() {
  try {
    state.cfg = await api("GET", "/api/status");
  } catch (e) {
    toast(`Can't reach the booth: ${e.message}`);
    setTimeout(init, 3000);
    return;
  }
  buildEditControls();
  $("btn-email").classList.toggle("hidden", !state.cfg.email);
  $("btn-sms").classList.toggle("hidden", !state.cfg.sms);
  $("btn-print").classList.toggle("hidden", !state.cfg.printer);

  $("start").onclick = startSession;
  $("caption-btn").onclick = async () => {
    const t = await askText({ title: "Add a caption", mode: "text", initial: state.settings.caption, max: 40 });
    if (t !== null) setSetting({ caption: t });
  };
  $("retake-all").onclick = startSession;
  $("to-share").onclick = () => { $("final").src = $("result").src; show("share"); };
  $("back-edit").onclick = () => show("edit");
  $("done").onclick = reset;
  $("btn-email").onclick = () => sendTo("email");
  $("btn-sms").onclick = () => sendTo("sms");
  $("btn-print").onclick = doPrint;
  $("btn-qr").onclick = showQr;
  $("qr-close").onclick = () => $("qr-modal").classList.add("hidden");
  show("attract");
}

init();
