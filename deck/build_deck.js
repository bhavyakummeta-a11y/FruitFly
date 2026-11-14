// Builds the FruitFly progress deck from deck/build/manifest.json (written by deck/build.py).
//   node deck/build_deck.js deck/build/manifest.json deck/FruitFly_Progress.pptx
// Layouts, theme and slide order live here; the story text lives in deck/content.json.
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");
const sizeOf = require("image-size");
const JSZip = require(require.resolve("jszip", { paths: [require.resolve("pptxgenjs")] }));

const [, , MANIFEST, OUT] = process.argv;
const M = JSON.parse(fs.readFileSync(MANIFEST, "utf8"));
const K = M.content || {};

// ---- theme ----------------------------------------------------------------------------
const THEME = {
  name: "FruitFly Cockpit",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "141821", lt1: "FFFFFF", dk2: "1B2433", lt2: "EEF2F6",
    accent1: "C8102E", // fly-eye red
    accent2: "F2B705", // hotspot amber
    accent3: "1F7A8C", // sky teal
    accent4: "3A9D5D", // ok green
    accent5: "6B7A8F", // slate
    accent6: "D97757", // Claude co-authored
    hlink: "1F7A8C", folHlink: "6B7A8F",
  },
};
const H = THEME.colors; // hex for hex-only options (charts, shadows, lines)

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = K.title || "FruitFly";
pres.author = "FruitFly team (auto-built)";
pres.company = "FruitFly";
const C = pres.SchemeColor;
const W = 13.333, HT = 7.5, MX = 0.6;
const built = (M.generated_utc || "").slice(0, 16).replace("T", " ") + " UTC";

// ---- layouts --------------------------------------------------------------------------
const footer = (dark) => [
  { text: { text: `FruitFly  ·  auto-built ${built} from sim logs @ ${M.commit}`,
            options: { x: MX, y: 7.05, w: 9, h: 0.3, fontSize: 10, color: dark ? H.lt2 : H.accent5, margin: 0 } } },
];
pres.defineSlideMaster({
  title: "TITLE", background: { color: H.dk2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: MX, y: 1.7, w: 6.2, h: 2.0, fontSize: 44, bold: true,
      color: H.lt1, fontFace: THEME.headFontFace, valign: "bottom", align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: MX, y: 3.85, w: 6.0, h: 1.1, fontSize: 18,
      color: H.lt2, valign: "top", align: "left", margin: 0 }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "SECTION", background: { color: H.dk2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 1.5, y: 2.55, w: 10.5, h: 1.2, fontSize: 40, bold: true,
      color: H.lt1, fontFace: THEME.headFontFace, valign: "bottom", align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 1.5, y: 3.9, w: 10.0, h: 1.3, fontSize: 18,
      color: H.lt2, valign: "top", align: "left", margin: 0 }, text: "" } },
    ...footer(true),
  ],
  slideNumber: { x: 12.2, y: 7.05, w: 0.6, h: 0.3, fontSize: 10, color: H.lt2 },
});
pres.defineSlideMaster({
  title: "CONTENT", background: { color: H.lt1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: MX, y: 0.35, w: 12.1, h: 0.8, fontSize: 36, bold: true,
      color: H.dk1, fontFace: THEME.headFontFace, valign: "middle", margin: 0 }, text: "" } },
    ...footer(false),
  ],
  slideNumber: { x: 12.2, y: 7.05, w: 0.6, h: 0.3, fontSize: 10, color: H.accent5 },
});

// ---- helpers --------------------------------------------------------------------------
let currentSection = "Overview";
function section(title) { currentSection = title; pres.addSection({ title }); }
function slide(master) { return pres.addSlide({ masterName: master, sectionTitle: currentSection }); }
const shadow = () => ({ type: "outer", color: "000000", opacity: 0.18, blur: 8, offset: 2, angle: 90 });
const clip = (s, n) => (!s ? "" : s.length <= n ? s : s.slice(0, n - 1).replace(/\s+\S*$/, "") + "…");
const hhmm = (iso) => (iso ? new Date(iso).toISOString().slice(11, 16) : "");
const exists = (p) => p && fs.existsSync(p);

function imgDims(p) {
  try { const d = sizeOf(p); return { w: d.width, h: d.height }; } catch { return { w: 4, h: 3 }; }
}
// Image fitted inside a box, on a rounded "mat" (the deck's frame motif).
function framed(s, p, x, y, w, h, name, dark) {
  const d = imgDims(p);
  const pad = 0.08;
  const r = Math.min((w - 2 * pad) / d.w, (h - 2 * pad) / d.h);
  const iw = d.w * r, ih = d.h * r;
  const ix = x + (w - iw) / 2, iy = y + (h - ih) / 2;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: ix - pad, y: iy - pad, w: iw + 2 * pad, h: ih + 2 * pad,
    fill: { color: dark ? C.text2 : C.background2 }, line: { type: "none" }, rectRadius: 0.08, shadow: shadow(),
    objectName: `${name} frame` });
  s.addImage({ path: p, x: ix, y: iy, w: iw, h: ih, objectName: name, altText: name });
  return { x: ix, y: iy, w: iw, h: ih };
}
function hex(s, x, y, size, color, label, name) {
  s.addShape(pres.shapes.HEXAGON, { x, y, w: size, h: size * 0.88, fill: { color }, line: { type: "none" },
    objectName: name || "hex marker" });
  if (label !== undefined) {
    s.addText(String(label), { x, y, w: size, h: size * 0.88, align: "center", valign: "middle", fontSize: 16,
      bold: true, color: C.background1, margin: 0, isTextBox: true, objectName: `${name || "hex"} label` });
  }
}
function stat(s, x, y, w, value, label, color) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h: 1.25, fill: { color: C.background2 }, line: { type: "none" },
    rectRadius: 0.08, objectName: `stat ${label}` });
  s.addText(String(value), { x: x + 0.15, y: y + 0.1, w: w - 0.3, h: 0.7, fontSize: 30, bold: true,
    color: color || C.text1, margin: 0, isTextBox: true, fit: "shrink", objectName: `stat ${label} value` });
  s.addText(label, { x: x + 0.15, y: y + 0.8, w: w - 0.3, h: 0.35, fontSize: 12, color: C.accent5, margin: 0,
    isTextBox: true, objectName: `stat ${label} label` });
}
const chartText = { catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", titleFontFace: "+mn-lt",
  dataLabelFontFace: "+mn-lt", legendFontFace: "+mn-lt", catAxisLabelColor: H.accent5, valAxisLabelColor: H.accent5,
  catAxisLabelFontSize: 11, valAxisLabelFontSize: 11, titleFontSize: 13, titleColor: H.dk1, legendFontSize: 11,
  valGridLine: { color: "DDE3EA", size: 0.75 }, catGridLine: { style: "none" } };
function flow(s, items, y, color, name) {
  const n = items.length, gap = 0.35, w = (W - 2 * MX - gap * (n - 1)) / n;
  items.forEach((it, i) => {
    const x = MX + i * (w + gap);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h: 1.55, fill: { color: C.background2 }, line: { type: "none" },
      rectRadius: 0.1, objectName: `${name} step ${i + 1}` });
    hex(s, x + 0.2, y + 0.2, 0.5, i === Math.floor(n / 2) ? C.accent1 : color, i + 1, `${name} step ${i + 1} marker`);
    s.addText(it.name, { x: x + 0.82, y: y + 0.2, w: w - 0.95, h: 0.45, fontSize: 16, bold: true, color: C.text1,
      margin: 0, valign: "middle", isTextBox: true, fit: "shrink", objectName: `${name} step ${i + 1} name` });
    s.addText(it.text, { x: x + 0.2, y: y + 0.8, w: w - 0.35, h: 0.65, fontSize: 13, color: C.text2, margin: 0,
      valign: "top", isTextBox: true, objectName: `${name} step ${i + 1} text` });
    if (i < n - 1) {
      s.addShape(pres.shapes.CHEVRON, { x: x + w + 0.09, y: y + 0.62, w: 0.17, h: 0.3,
        fill: { color: C.accent5 }, line: { type: "none" }, objectName: `${name} arrow ${i + 1}` });
    }
  });
}

// ---- data -----------------------------------------------------------------------------
const sessions = M.sessions || [];
const runs = M.runs || [];
const commits = M.commits || [];
const allMedia = [...sessions, ...runs, ...(M.loose_media || [])].flatMap((e) => e.images || []);
const agentShots = allMedia.filter((i) => i.kind === "agent" || i.kind === "screen");
const pageShots = allMedia.filter((i) => i.kind === "page");
const runLabel = (e) => e.name || `${e.backend || "?"} / ${e.brain || "?"} run, ${hhmm(e.utc)} UTC`;
const notes = [...sessions, ...runs].flatMap((e) => (e.notes || []).map((n) => ({ ...n, run: runLabel(e) })));
const maxOf = (arr) => { const v = (arr || []).filter((x) => typeof x === "number"); return v.length ? Math.max(...v) : null; };

// ---- 1. title -------------------------------------------------------------------------
{
  section("Overview");
  const s = slide("TITLE");
  s.addText(K.title || "Fly Brains Fly a Plane", { placeholder: "title" });
  s.addText(K.subtitle || "", { placeholder: "body" });
  s.addText(`${M.all_sessions} FlightGear sessions  ·  ${runs.length} controller runs  ·  ${commits.length} commits  ·  ${(M.people || []).length} people + Claude agents`,
    { x: MX, y: 5.35, w: 6.2, h: 0.4, fontSize: 14, color: C.accent2, margin: 0, isTextBox: true, objectName: "title stats" });
  s.addText(`Auto-built ${built}`, { x: MX, y: 5.8, w: 6.2, h: 0.35, fontSize: 12, color: C.background2, margin: 0,
    isTextBox: true, objectName: "title build stamp" });
  if (exists(M.hero)) framed(s, M.hero, 7.2, 0.9, 5.6, 5.7, "hero screenshot", true);
  s.addNotes("Title. Every number on this slide and every screenshot in this deck comes from the project's own logs: the sim-logs branch (one folder per FlightGear session or controller run), the git history, and screenshots captured automatically while FlightGear runs. Rebuild with: python -m flight_simulator.media deck");
}

// ---- 2. what we're building -----------------------------------------------------------
{
  const s = slide("CONTENT");
  s.addText("A fly brain sits where the pilot would", { placeholder: "title" });
  flow(s, K.pipeline || [], 1.45, C.accent3, "pipeline");
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: MX, y: 3.35, w: 5.2, h: 3.35, fill: { color: C.text2 }, line: { type: "none" },
    rectRadius: 0.1, objectName: "rule card" });
  s.addText("Rule #1: honor the fly brain", { x: MX + 0.3, y: 3.55, w: 4.6, h: 0.5, fontSize: 20, bold: true,
    color: C.accent2, fontFace: THEME.headFontFace, margin: 0, isTextBox: true, objectName: "rule title" });
  s.addText(K.rule || "", { x: MX + 0.3, y: 4.15, w: 4.6, h: 2.35, fontSize: 16, color: C.background1, margin: 0,
    valign: "top", isTextBox: true, objectName: "rule text" });
  (K.goals || []).forEach((g, i) => {
    const x = 6.15, y = 3.35 + i * 1.15;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 6.58, h: 1.0, fill: { color: C.background2 }, line: { type: "none" },
      rectRadius: 0.08, objectName: `goal ${g.tier}` });
    s.addText(g.tier.toUpperCase(), { x: x + 0.2, y: y + 0.12, w: 1.3, h: 0.35, fontSize: 12, bold: true,
      color: [C.accent1, C.accent3, C.accent6][i] || C.accent5, margin: 0, isTextBox: true, objectName: `goal ${g.tier} tier` });
    s.addText(g.name, { x: x + 0.2, y: y + 0.45, w: 1.9, h: 0.45, fontSize: 15, bold: true, color: C.text1, margin: 0,
      isTextBox: true, fit: "shrink", objectName: `goal ${g.tier} name` });
    s.addText(g.text, { x: x + 2.2, y: y + 0.1, w: 4.2, h: 0.8, fontSize: 14, color: C.text2, margin: 0, valign: "middle",
      isTextBox: true, objectName: `goal ${g.tier} text` });
  });
  s.addNotes("The pipeline: FlightGear state is encoded as sensory firing rates, the whole-brain LIF model (Shiu et al. 2024 on FlyWire wiring) runs one trial while the sim is paused, and named descending neurons are decoded into controls. The rule keeps us honest: the wiring does the work, thin encoders and decoders around it, always against a baseline.");
}

// ---- 3. how we work -------------------------------------------------------------------
{
  const s = slide("CONTENT");
  s.addText("Every flight is named, logged, pushed and filmed", { placeholder: "title" });
  flow(s, K.workflow || [], 1.45, C.accent5, "workflow");
  const shots = allMedia.length;
  stat(s, MX, 3.35, 2.6, M.all_sessions, "FlightGear sessions logged", C.accent3);
  stat(s, MX + 2.8, 3.35, 2.6, runs.length, "controller runs logged", C.accent3);
  stat(s, MX, 4.8, 2.6, notes.length, "feedback notes", C.accent1);
  stat(s, MX + 2.8, 4.8, 2.6, shots, "screenshots captured", C.accent6);
  const shot = pageShots[pageShots.length - 1] || agentShots[agentShots.length - 1];
  if (shot && exists(shot.path)) {
    framed(s, shot.path, 6.3, 3.3, 6.43, 3.6, "workflow screenshot");
  } else {
    s.addText([{ text: "How to add to this deck", options: { bold: true, breakLine: true, fontSize: 16, color: C.text1 } },
      { text: (K.how_to_add || "").split("  |  ").join("\n"), options: { fontSize: 13, color: C.text2 } }],
    { x: 6.3, y: 3.35, w: 6.43, h: 2.7, margin: 0.2, fill: { color: C.background2 }, valign: "top", isTextBox: true,
      objectName: "how to add" });
  }
  s.addNotes("Process slide. The watchdog attaches a logger to every FlightGear process; the media recorder screenshots FlightGear every 20 s and on notable events, and the live log page every 90 s. Agents snap their own terminal with media snap --window. All of it lands on the sim-logs branch, and this deck is rebuilt from it. " + (K.how_to_add || ""));
}

// ---- section: flight log ----------------------------------------------------------------
{
  section("Flight log");
  const s = slide("SECTION");
  s.addText("Flight log", { placeholder: "title" });
  s.addText("Every session and controller run in order, with the screenshots, telemetry and notes captured at the time.",
    { placeholder: "body" });
  hex(s, MX, 2.75, 0.7, C.accent1, 1, "section 1 marker");
  s.addNotes("Section divider: the chronological record.");
}

// ---- timeline -------------------------------------------------------------------------
{
  const items = [...sessions.map((e) => ({ ...e, type: "session" })), ...runs.map((e) => ({ ...e, type: "run" }))]
    .filter((e) => e.utc);
  if (items.length) {
    const s = slide("CONTENT");
    s.addText("The day so far, run by run", { placeholder: "title" });
    const t = (e) => new Date(e.utc).getTime();
    const ends = items.map((e) => t(e) + 1000 * (e.duration_s || e.elapsed_s || 60));
    const t0 = Math.min(...items.map(t)), t1 = Math.max(...ends);
    const span = Math.max(t1 - t0, 30 * 60e3);
    const people = [...new Set(items.map((e) => e.who))];
    const X0 = 2.6, X1 = W - MX, Y0 = 1.6, laneH = Math.min(1.0, 4.3 / people.length);
    const xOf = (ms) => X0 + ((ms - t0) / span) * (X1 - X0);
    people.forEach((p, i) => {
      const y = Y0 + i * laneH;
      s.addShape(pres.shapes.RECTANGLE, { x: X0, y, w: X1 - X0, h: laneH - 0.12, fill: { color: C.background2 },
        line: { type: "none" }, objectName: `lane ${p}` });
      s.addText(p, { x: MX, y, w: 1.9, h: laneH - 0.12, fontSize: 14, bold: true, color: C.text1, margin: 0,
        valign: "middle", isTextBox: true, objectName: `lane ${p} label` });
    });
    items.forEach((e, k) => {
      const y = Y0 + people.indexOf(e.who) * laneH;
      if (e.type === "session") {
        const x = xOf(t(e)), w = Math.max(0.12, xOf(t(e) + 1000 * (e.duration_s || 60)) - x);
        s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: y + 0.08, w, h: laneH * 0.42, rectRadius: 0.05,
          fill: { color: e.exit_code ? C.accent1 : C.accent3, transparency: 15 }, line: { type: "none" },
          objectName: `session ${k}` });
      } else {
        const ok = e.exit_code === 0 && !e.collision;
        const d = 0.2;
        s.addShape(pres.shapes.OVAL, { x: xOf(t(e)) - d / 2, y: y + laneH * 0.55, w: d, h: d,
          fill: { color: ok ? C.accent4 : e.exit_code === undefined || e.exit_code === null ? C.accent5 : C.accent1 },
          line: { color: H.lt1, width: 0.75 }, objectName: `run ${k}` });
      }
    });
    const stepMin = span > 3 * 3600e3 ? 60 : span > 90 * 60e3 ? 30 : 15;
    const first = Math.ceil(t0 / (stepMin * 60e3)) * stepMin * 60e3;
    const yAxis = Y0 + people.length * laneH + 0.02;
    for (let ms = first; ms <= t0 + span; ms += stepMin * 60e3) {
      s.addText(new Date(ms).toISOString().slice(11, 16), { x: xOf(ms) - 0.4, y: yAxis, w: 0.8, h: 0.3, fontSize: 11,
        color: C.accent5, align: "center", margin: 0, isTextBox: true, objectName: `tick ${ms}` });
    }
    const ly = 6.45;
    [["FlightGear session", C.accent3, "bar"], ["session crashed / force-closed", C.accent1, "bar"],
     ["controller run OK", C.accent4, "dot"], ["controller run failed", C.accent1, "dot"]].forEach(([label, col, kind], i) => {
      const x = X0 + i * 2.6;
      if (kind === "bar") s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: ly + 0.07, w: 0.35, h: 0.18, rectRadius: 0.04,
        fill: { color: col }, line: { type: "none" }, objectName: `legend ${label}` });
      else s.addShape(pres.shapes.OVAL, { x: x + 0.08, y: ly + 0.06, w: 0.2, h: 0.2, fill: { color: col }, line: { type: "none" },
        objectName: `legend ${label}` });
      s.addText(label, { x: x + 0.45, y: ly, w: 2.1, h: 0.32, fontSize: 11, color: C.text2, margin: 0, valign: "middle",
        isTextBox: true, objectName: `legend ${label} text` });
    });
    s.addText("UTC", { x: MX, y: yAxis, w: 1.9, h: 0.3, fontSize: 11, color: C.accent5, margin: 0, isTextBox: true,
      objectName: "axis unit" });
    s.addNotes(`Timeline: ${sessions.length} FlightGear sessions (bars, length = duration) and ${runs.length} controller runs (dots) by person. Red marks a crash, force-close or failed run; the failure reasons are on the results slides and in each run's feedback.md.`);
  }
}

// ---- session slides -------------------------------------------------------------------
// Sessions with footage or notes get their own slide; the rest share small-multiple grids.
const featured = sessions.filter((e) => (e.hero && exists(e.hero.path)) || (e.notes || []).length);
const quiet = sessions.filter((e) => !featured.includes(e) && e.series);
for (let p = 0; p * 6 < quiet.length; p++) {
  const s = slide("CONTENT");
  const group = quiet.slice(p * 6, p * 6 + 6);
  s.addText(`Sessions without footage yet${quiet.length > 6 ? ` (${p + 1}/${Math.ceil(quiet.length / 6)})` : ""}`, { placeholder: "title" });
  group.forEach((e, i) => {
    const x = MX + (i % 3) * 4.1, y = 1.35 + Math.floor(i / 3) * 2.85;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 3.9, h: 2.65, fill: { color: C.background2 }, line: { type: "none" },
      rectRadius: 0.08, objectName: `quiet session ${i + 1}` });
    s.addText(clip(e.name, 38), { x: x + 0.15, y: y + 0.1, w: 3.6, h: 0.35, fontSize: 14, bold: true, color: C.text1,
      margin: 0, isTextBox: true, fit: "shrink", objectName: `quiet session ${i + 1} name` });
    const dur = e.duration_s != null ? `${Math.floor(e.duration_s / 60)}:${String(e.duration_s % 60).padStart(2, "0")}` : "–";
    s.addText(`${hhmm(e.utc)} UTC · ${e.who.split(" ")[0]} · ${dur} min · ${e.exit_code ? "crashed / force-closed" : "closed"}`,
      { x: x + 0.15, y: y + 0.45, w: 3.6, h: 0.3, fontSize: 11, color: e.exit_code ? C.accent1 : C.accent5, margin: 0,
        isTextBox: true, objectName: `quiet session ${i + 1} meta` });
    s.addChart(pres.charts.LINE, [{ name: "Altitude (ft)", labels: e.series.t_s.map(String), values: e.series.alt_ft }],
      { x: x + 0.05, y: y + 0.8, w: 3.8, h: 1.8, ...chartText, catAxisLabelFontSize: 9, valAxisLabelFontSize: 9,
        showTitle: false, showLegend: false, chartColors: [H.accent3], lineSize: 2, lineDataSymbol: "none",
        catAxisHidden: true, objectName: `quiet session ${i + 1} altitude` });
  });
  s.addNotes("Altitude (ft) over each session, for sessions logged before the media recorder existed or without notes. " +
    group.map((e) => `${e.name}: ${e.id}`).join("; "));
}
featured.forEach((e, i) => {
  const ser = e.series;
  const hasMedia = e.hero && exists(e.hero.path);
  const s = slide("CONTENT");
  s.addText(clip(e.name, 46), { placeholder: "title" });
  const tel = (e.images || []).map((x) => x.telemetry || {});   // fallback: telemetry stamped on screenshots
  const maxAlt = ser ? maxOf(ser.alt_ft) : maxOf(tel.map((t) => t.alt_ft));
  const maxIas = ser ? maxOf(ser.ias_kt) : maxOf(tel.map((t) => t.ias_kt));
  const dur = e.duration_s != null ? `${Math.floor(e.duration_s / 60)}:${String(e.duration_s % 60).padStart(2, "0")}` : "–";
  const sub = `${hhmm(e.utc)} UTC  ·  ${e.who}  ·  ${e.aircraft || "aircraft ?"}  ·  ${e.outcome}`;
  s.addText(sub, { x: MX, y: 1.12, w: 12.1, h: 0.35, fontSize: 14, color: e.exit_code ? C.accent1 : C.accent5, margin: 0,
    isTextBox: true, objectName: "session subtitle" });
  const note = (e.notes || [])[e.notes.length - 1];
  if (hasMedia) {
    framed(s, e.hero.path, MX, 1.6, 7.5, 5.25, "session screenshot");
    const x = 8.45;
    stat(s, x, 1.65, 2.05, dur, "duration (min:s)");
    stat(s, x + 2.2, 1.65, 2.05, maxAlt != null ? Math.round(maxAlt).toLocaleString("en-US") : "–", "max altitude, ft", C.accent3);
    stat(s, x, 3.05, 2.05, maxIas != null ? Math.round(maxIas) : "–", "max airspeed, kt", C.accent3);
    stat(s, x + 2.2, 3.05, 2.05, (e.images || []).length, "screenshots", C.accent6);
    if (note) {
      s.addText([{ text: `${note.who}: `, options: { bold: true } }, { text: clip(note.text, 300) }],
        { x, y: 4.5, w: 4.25, h: 2.35, fontSize: 14, color: C.text2, margin: 0, valign: "top", isTextBox: true,
          objectName: "session note" });
    } else if (ser) {
      s.addChart(pres.charts.LINE, [{ name: "Altitude (ft)", labels: ser.t_s.map(String), values: ser.alt_ft }],
        { x, y: 4.45, w: 4.25, h: 2.4, ...chartText, showTitle: true, title: "Altitude, ft (x: seconds)", showLegend: false,
          chartColors: [H.accent3], lineSize: 2, lineDataSymbol: "none", catAxisLabelFrequency: Math.ceil(ser.t_s.length / 6),
          objectName: "altitude chart" });
    }
  } else {
    if (ser) {
      s.addChart(pres.charts.LINE, [{ name: "Altitude (ft)", labels: ser.t_s.map(String), values: ser.alt_ft }],
        { x: MX, y: 1.65, w: 7.6, h: 2.55, ...chartText, showTitle: true, title: "Altitude, ft (x: seconds since start)",
          showLegend: false, chartColors: [H.accent3], lineSize: 2, lineDataSymbol: "none",
          catAxisLabelFrequency: Math.ceil(ser.t_s.length / 8), objectName: "altitude chart" });
      s.addChart(pres.charts.LINE, [{ name: "Airspeed (kt)", labels: ser.t_s.map(String), values: ser.ias_kt }],
        { x: MX, y: 4.3, w: 7.6, h: 2.55, ...chartText, showTitle: true, title: "Indicated airspeed, kt", showLegend: false,
          chartColors: [H.accent1], lineSize: 2, lineDataSymbol: "none",
          catAxisLabelFrequency: Math.ceil(ser.t_s.length / 8), objectName: "airspeed chart" });
    }
    const x = 8.55;
    stat(s, x, 1.65, 2.0, dur, "duration (min:s)");
    stat(s, x + 2.15, 1.65, 2.0, e.samples ?? "–", "telemetry samples", C.accent3);
    s.addText(note ? [{ text: `${note.who}: `, options: { bold: true } }, { text: clip(note.text, 420) }]
      : [{ text: "No screenshots or notes for this session yet. ", options: { bold: true } },
         { text: "Sessions from now on are filmed automatically; add a note with runlog note \"...\"." }],
    { x, y: 3.1, w: 4.15, h: 3.75, fontSize: 14, color: C.text2, margin: 0, valign: "top", isTextBox: true,
      objectName: "session note" });
  }
  s.addNotes(`${e.name} (${e.id}). ${sub}. ${(e.notes || []).map((n) => `${n.who} (${n.when}): ${n.text}`).join(" ")}`
    + (hasMedia ? ` Screenshot caption: ${e.hero.caption || "none"}.` : ""));
  if (e.gif && exists(e.gif)) {
    const g = slide("CONTENT");
    g.addText(`Time-lapse: ${clip(e.name, 34)}`, { placeholder: "title" });
    framed(g, e.gif, MX, 1.3, 12.1, 5.55, "session time-lapse");
    g.addNotes(`Animated time-lapse of ${(e.images || []).filter((x) => x.kind === "fg").length} FlightGear frames (plays in slideshow mode). Frames are 20 s apart plus extra frames on events; each carries the telemetry banner and event caption at the time.`);
  }
});

// ---- section: results -----------------------------------------------------------------
section("Results");
{
  const s = slide("SECTION");
  s.addText("What worked, what broke", { placeholder: "title" });
  s.addText("Controller outcomes against the baseline, the bugs we hit, and what the fly can see.", { placeholder: "body" });
  hex(s, MX, 2.75, 0.7, C.accent1, 2, "section 2 marker");
  s.addNotes("Section divider: results.");
}
{
  const s = slide("CONTENT");
  s.addText("Controller runs: obstacle clearance by brain", { placeholder: "title" });
  const done = runs.filter((r) => typeof r.min_clearance_m === "number");
  const ok = runs.filter((r) => r.exit_code === 0 && !r.collision).length;
  const coll = runs.filter((r) => r.collision).length;
  const err = runs.filter((r) => r.exit_code && r.exit_code !== 0 && r.exit_code !== 2).length;
  if (done.length) {
    s.addChart(pres.charts.BAR, [{ name: "Minimum clearance (m)", labels: done.map((r) => `${hhmm(r.utc)} ${r.brain} · ${r.backend}`),
      values: done.map((r) => r.min_clearance_m) }],
    { x: MX, y: 1.4, w: 7.9, h: 5.4, barDir: "bar", ...chartText, showTitle: true, title: "Minimum obstacle clearance, m",
      showLegend: false, chartColors: [H.accent3], showValue: true, dataLabelPosition: "outEnd", dataLabelColor: H.dk1,
      dataLabelFontSize: 11, dataLabelFormatCode: "0", objectName: "clearance chart" });
  }
  const x = 8.85;
  stat(s, x, 1.45, 1.85, runs.length, "runs");
  stat(s, x + 2.0, 1.45, 1.85, ok, "completed", C.accent4);
  stat(s, x, 2.85, 1.85, coll, "collisions", C.accent1);
  stat(s, x + 2.0, 2.85, 1.85, err, "errors", C.accent1);
  const errs = [...new Set(runs.map((r) => r.error).filter(Boolean))].slice(-3);
  s.addText(errs.length ? [{ text: "Most recent failures", options: { bold: true, breakLine: true, color: C.text1 } },
    ...errs.map((t, i) => ({ text: clip(t, 110), options: { bullet: true, breakLine: i < errs.length - 1 } }))]
    : "No failed runs.", { x, y: 4.3, w: 3.85, h: 2.55, fontSize: 12, color: C.text2, margin: 0, valign: "top",
    paraSpaceAfter: 4, isTextBox: true, objectName: "failure list" });
  s.addNotes(`Controller runs with a measured clearance (demo and FlightGear backends). Reflex is the non-neural baseline, silent disables the escape channel, connectome is the real LIF model. ${runs.length} runs: ${ok} completed, ${coll} collisions, ${err} errors. Errors: ${errs.join(" | ")}`);
}
{
  const picks = notes.filter((n) => /root cause|fix|fail|bug|broke|crash|didn.t|does not|wrong/i.test(n.text)).slice(-4);
  if (picks.length) {
    const s = slide("CONTENT");
    s.addText("Bugs we found by flying", { placeholder: "title" });
    picks.forEach((n, i) => {
      const x = MX + (i % 2) * 6.15, y = 1.45 + Math.floor(i / 2) * 2.75;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 5.95, h: 2.55, fill: { color: C.background2 }, line: { type: "none" },
        rectRadius: 0.08, objectName: `lesson ${i + 1}` });
      hex(s, x + 0.2, y + 0.2, 0.45, C.accent1, i + 1, `lesson ${i + 1} marker`);
      s.addText(clip(n.run, 55), { x: x + 0.8, y: y + 0.18, w: 4.95, h: 0.45, fontSize: 14, bold: true, color: C.text1,
        margin: 0, valign: "middle", isTextBox: true, objectName: `lesson ${i + 1} run` });
      s.addText(clip(n.text, 250), { x: x + 0.25, y: y + 0.75, w: 5.45, h: 1.65, fontSize: 14, color: C.text2, margin: 0,
        valign: "top", isTextBox: true, objectName: `lesson ${i + 1} text` });
    });
    s.addNotes("Notes written into run logs (feedback.md) that name a failure or a fix, newest last:\n" +
      picks.map((n) => `${n.who} (${n.when}) on ${n.run}: ${n.text}`).join("\n"));
  }
}
(M.repo_images || []).filter((r) => r.kind === "cockpit").forEach((r) => {
  const s = slide("CONTENT");
  s.addText("What the fly could see: clickable cockpit controls", { placeholder: "title" });
  framed(s, r.path, MX, 1.35, 7.9, 5.5, "cockpit hotspots");
  stat(s, 8.85, 1.45, 3.85, r.count, `clickable controls located (${r.aircraft})`, C.accent2);
  s.addText([{ text: "FlightGear outlines every clickable control in yellow (Ctrl-C).", options: { breakLine: true, bullet: true } },
    { text: "We find each yellow region and record its direction from the pilot's eye (azimuth / elevation).", options: { breakLine: true, bullet: true } },
    { text: "Directions are what a fly's eye works in, so they can drive its visual inputs directly.", options: { bullet: true } }],
  { x: 8.85, y: 2.95, w: 3.85, h: 3.9, fontSize: 14, color: C.text2, margin: 0, valign: "top", paraSpaceAfter: 8,
    isTextBox: true, objectName: "cockpit text" });
  s.addNotes("Cockpit perception: cockpit/<aircraft>/hotspots.json lists each region's pixel box and direction. Names are not attached yet; that is a next step.");
});

// ---- section: agents ------------------------------------------------------------------
section("Agents along the way");
{
  const s = slide("SECTION");
  s.addText("Agents along the way", { placeholder: "title" });
  s.addText("People and Claude agents working the same repo at once: who built what, when, and how they kept out of each other's way.",
    { placeholder: "body" });
  hex(s, MX, 2.75, 0.7, C.accent1, 3, "section 3 marker");
  s.addNotes("Section divider: the people and agents.");
}
if (commits.length) {
  const s = slide("CONTENT");
  s.addText("Commits per half hour: humans and Claude", { placeholder: "title" });
  const bucket = (iso) => { const d = new Date(iso); d.setUTCMinutes(d.getUTCMinutes() < 30 ? 0 : 30, 0, 0); return d.getTime(); };
  const b0 = bucket(commits[0].utc), b1 = bucket(commits[commits.length - 1].utc);
  const labels = [], human = [], claude = [];
  for (let b = b0; b <= b1; b += 30 * 60e3) {
    labels.push(new Date(b).toISOString().slice(11, 16));
    human.push(commits.filter((c) => bucket(c.utc) === b && !c.claude).length);
    claude.push(commits.filter((c) => bucket(c.utc) === b && c.claude).length);
  }
  const keep = labels.length > 48 ? labels.length - 48 : 0;
  s.addChart(pres.charts.BAR, [{ name: "Claude co-authored", labels: labels.slice(keep), values: claude.slice(keep) },
    { name: "Human only", labels: labels.slice(keep), values: human.slice(keep) }],
  { x: MX, y: 1.4, w: 8.3, h: 5.45, barDir: "col", barGrouping: "stacked", ...chartText, showTitle: true,
    title: "Commits on main (UTC, half-hour buckets)", showLegend: true, legendPos: "b", chartColors: [H.accent6, H.accent5],
    objectName: "commit chart" });
  const nClaude = commits.filter((c) => c.claude).length;
  const agents = new Set((M.tickets || []).map((t) => t.agent).filter(Boolean));
  const x = 9.15;
  stat(s, x, 1.45, 3.55, commits.length, "commits on main");
  stat(s, x, 2.85, 3.55, `${Math.round((100 * nClaude) / commits.length)}%`, "co-authored by Claude", C.accent6);
  stat(s, x, 4.25, 3.55, (M.people || []).length, "people in the logs", C.accent3);
  stat(s, x, 5.65, 3.55, (M.tickets || []).length, `tickets on the board${agents.size ? ` (${agents.size} agents)` : ""}`, C.accent1);
  s.addNotes(`Commit history of main (merges excluded). A commit counts as Claude co-authored when its message carries a Co-Authored-By: Claude trailer. Latest commits: ${commits.slice(-5).map((c) => `${c.hash} ${c.subject}`).join("; ")}`);
}
if ((M.tickets || []).length) {
  const s = slide("CONTENT");
  s.addText("The ticket board keeps agents off each other's files", { placeholder: "title" });
  const rows = (M.tickets || []).slice(-10);
  const head = ["#", "State", "Agent", "Task"].map((t) => ({ text: t, options: { bold: true, color: H.lt1, fill: { color: H.dk2 } } }));
  s.addTable([head, ...rows.map((t) => [String(t.id), t.state, t.agent || "–", clip(t.task, 95)])],
    { x: MX, y: 1.45, w: 12.1, colW: [0.6, 1.3, 1.9, 8.3], fontSize: 13, color: H.dk1, border: { type: "solid", pt: 0.5, color: "DDE3EA" },
      fill: { color: H.lt1 }, rowH: 0.42, valign: "middle", objectName: "ticket table" });
  s.addNotes("tickets.py: a shared local board. Agents claim a task plus the paths they will edit; a second agent asking for the same paths is blocked. Claims are leases that expire if not renewed.");
}
if (agentShots.length) {
  const shots = agentShots.slice(-4);
  const s = slide("CONTENT");
  s.addText("Agents at work", { placeholder: "title" });
  const n = shots.length, cols = n === 1 ? 1 : 2, rows = Math.ceil(n / cols);
  const cw = (12.1 - (cols - 1) * 0.3) / cols, ch = (5.5 - (rows - 1) * 0.3) / rows;
  shots.forEach((sh, i) => {
    const x = MX + (i % cols) * (cw + 0.3), y = 1.35 + Math.floor(i / cols) * (ch + 0.3);
    framed(s, sh.path, x, y, cw, ch, `agent snapshot ${i + 1}`);
  });
  s.addNotes("Snapshots of Claude agent terminals, taken with media snap --window. Captions: " + shots.map((x) => `${hhmm(x.utc)} ${x.caption}`).join("; "));
}
if (pageShots.length) {
  const sh = pageShots[pageShots.length - 1];
  const s = slide("CONTENT");
  s.addText("The live session page, as it looked", { placeholder: "title" });
  framed(s, sh.path, MX, 1.3, 12.1, 5.55, "live log page");
  s.addNotes(`Automatic screenshot of the session's live page at ${hhmm(sh.utc)} UTC: airplane and fly-activity charts plus the running event log.`);
}

// ---- close ----------------------------------------------------------------------------
section("Next");
{
  const s = slide("SECTION");
  s.addText("Next steps", { placeholder: "title" });
  s.addText((K.next_steps || []).map((t, i, a) => ({ text: t, options: { bullet: { type: "number" }, breakLine: i < a.length - 1 } })),
    { x: 1.5, y: 3.9, w: 10.5, h: 2.6, fontSize: 18, color: H.lt2, margin: 0, valign: "top", paraSpaceAfter: 6,
      isTextBox: true, objectName: "next steps" });
  hex(s, MX, 2.75, 0.7, C.accent2, "→", "section next marker");
  s.addNotes("Next steps, from deck/content.json. " + (K.how_to_add || ""));
}

// ---- appendix -------------------------------------------------------------------------
section("Appendix");
{
  const all = [...sessions.map((e) => [hhmm(e.utc), e.who, "session", clip(e.name, 60), e.outcome]),
    ...runs.map((e) => [hhmm(e.utc), e.who, "run", `${e.backend || "?"} / ${e.brain || "?"}`,
      e.collision ? "collision" : e.exit_code === 0 ? "completed" : e.exit_code == null ? "–" : `exit ${e.exit_code}`])]
    .sort((a, b) => a[0].localeCompare(b[0]));
  const per = Math.ceil(all.length / Math.ceil(all.length / 12));   // balanced pages, at most 12 rows
  for (let p = 0; p * per < all.length; p++) {
    const s = slide("CONTENT");
    s.addText(`Run index${all.length > per ? ` (${p + 1}/${Math.ceil(all.length / per)})` : ""}`, { placeholder: "title" });
    const head = ["UTC", "Who", "Kind", "Session / controller", "Outcome"].map((t) => ({ text: t,
      options: { bold: true, color: H.lt1, fill: { color: H.dk2 } } }));
    s.addTable([head, ...all.slice(p * per, (p + 1) * per)], { x: MX, y: 1.4, w: 12.1, colW: [0.9, 2.0, 1.1, 5.8, 2.3],
      fontSize: 12, color: H.dk1, rowH: 0.4, border: { type: "solid", pt: 0.5, color: "DDE3EA" }, valign: "middle",
      objectName: "run index" });
    s.addNotes("Every logged run. Full logs: the sim-logs branch, runs/<run id>/ (feedback.md, airplane.csv, events.log, media/).");
  }
}

// ---- write + theme ----------------------------------------------------------------------
(async () => {
  await pres.writeFile({ fileName: OUT });
  const zip = await JSZip.loadAsync(fs.readFileSync(OUT));
  const tp = Object.keys(zip.files).find((f) => /^ppt\/theme\/theme\d+\.xml$/.test(f));
  let xml = await zip.file(tp).async("string");
  for (const [slot, val] of Object.entries(THEME.colors)) {
    xml = xml.replace(new RegExp(`<a:${slot}>[\\s\\S]*?</a:${slot}>`), `<a:${slot}><a:srgbClr val="${val}"/></a:${slot}>`);
  }
  xml = xml.replace(/<a:clrScheme name="[^"]*"/, `<a:clrScheme name="${THEME.name}"`);
  zip.file(tp, xml);
  for (const f of Object.keys(zip.files).filter((f) => /^ppt\/charts\/chart\d+\.xml$/.test(f))) {
    const c = await zip.file(f).async("string");
    zip.file(f, c.replace(/<c:crossesAt val="autoZero"\/>/g, '<c:crosses val="autoZero"/>'));
  }
  // Copy files only: folder entries break cloud co-editing (zip.remove on a folder would drop its files too).
  const clean = new JSZip();
  for (const [name, f] of Object.entries(zip.files)) {
    if (!f.dir) clean.file(name, await f.async("nodebuffer"), { createFolders: false });
  }
  fs.writeFileSync(OUT, await clean.generateAsync({ type: "nodebuffer", compression: "DEFLATE" }));
  console.log(`wrote ${OUT} (${pres.slides.length} slides)`);
})();
