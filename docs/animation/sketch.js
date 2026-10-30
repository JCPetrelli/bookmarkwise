// Bookmarkwise README animation (p5.js). Every bookmark here is invented.
// Deterministic: frame n always draws the same picture, so it can be rendered
// to a GIF frame by frame (see render.mjs). Open index.html to watch it live.

const W = 1200, H = 675, FPS = 24, DURATION = 11.5; // seconds, then it loops
const C = {
  bg: "#16171a", win: "#1f2127", bar: "#24262d", line: "#2e3138", text: "#ececec",
  muted: "#8f9199", dim: "#5d6068", accent: "#e8925a", ok: "#7cc47f", bad: "#e06c6c",
};
const SANS = "Helvetica Neue, Helvetica, Arial, sans-serif";
const MONO = "Menlo, ui-monospace, monospace";

// The "Work" folder: [before, after or null for deleted, dot colour]
const ROWS = [
  ["Harbor API - Confluence", "Confluence · Harbor API", "#5b8def"],
  ["Harbor API - Confluence", null, "#5b8def"],
  ["Board", "Jira · Board (filter 12)", "#4c7bd9"],
  ["Board", "Jira · Board (filter 19)", "#4c7bd9"],
  ["localhost:3000", null, "#777b85"],
  ["Harbor staging", "Env · Harbor staging", "#9a8cd8"],
  ["Sign in - Harbor Admin", "Env · Harbor admin", "#9a8cd8"],
  ["view-source:https://harbor.example.org/", null, "#777b85"],
  ["Q3 roadmap - Google Sheets", "Sheets · Q3 roadmap", "#4fae6f"],
];
// Bookmarks bar chips: [before, after or null, folder?]
const CHIPS = [
  ["Inbox (12) - mail.example.org", "Mail · Inbox", false],
  ["ACME CORP - SPRINT BOARD - Agile Board - Jira", "Jira · Sprint board", false],
  ["Sprint board", null, false],
  ["Work", "Work", true],
  ["Reading", "Reading", true],
];
const CHAT = [
  { at: 0.4, type: true, parts: [[C.accent, "> "], [C.text, "clean up my bookmarks"]] },
  { at: 2.0, parts: [[C.muted, "… 25 bookmarks · 4 duplicates · 3 junk links"]] },
  { at: 3.0, parts: [[C.muted, "? Name them how?  "], [C.accent, "Tool · What it is"]] },
  { at: 4.2, parts: [[C.ok, "● "], [C.text, "Plan approved: 9 delete · 15 rename"]] },
  { at: 5.0, parts: [[C.muted, "apply: backup ✓  check ✓"]] },
  { at: 8.6, parts: [[C.ok, "● "], [C.text, "Applied 28 · verified"]] },
];

// Timeline (seconds)
const T_FLAG = 2.0, T_STRIKE = 5.4, T_COLLAPSE = 6.0, T_RETYPE = 6.4, T_SORT = 7.8, T_FADE = 10.9;

let frameNo = null; // set by render.mjs; null = live playback

function setup() {
  createCanvas(W, H);
  pixelDensity(1);
  frameRate(FPS);
  textFont(SANS);
}

function draw() {
  const f = frameNo === null ? frameCount - 1 : frameNo;
  drawFrame((f / FPS) % DURATION);
}

window.renderFrame = (n) => { frameNo = n; redraw(); return document.querySelector("canvas").toDataURL("image/png"); };
window.FRAMES = Math.round(DURATION * FPS);

const ease = (x) => (x <= 0 ? 0 : x >= 1 ? 1 : x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
const clamp01 = (x) => Math.max(0, Math.min(1, x));
const prog = (t, a, d) => ease(clamp01((t - a) / d));

// Backspace the old title, then type the new one.
function retype(before, after, p) {
  if (p <= 0 || before === after) return before;
  if (p >= 1) return after;
  if (p < 0.45) return before.slice(0, Math.round(before.length * (1 - p / 0.45)));
  return after.slice(0, Math.round(after.length * ((p - 0.45) / 0.55)));
}

function fit(s, maxW) {
  if (textWidth(s) <= maxW) return s;
  while (s.length && textWidth(s + "…") > maxW) s = s.slice(0, -1);
  return s + "…";
}

function drawFrame(t) {
  background(C.bg);
  const fadeIn = prog(t, 0, 0.35), fadeOut = 1 - prog(t, T_FADE, 0.6);
  const alpha = Math.min(fadeIn, fadeOut);

  push();
  drawingContext.globalAlpha = alpha;
  headline();
  windowFrame();
  bar(t);
  folder(t);
  chat(t);
  footer();
  pop();
}

function headline() {
  textFont(SANS);
  textStyle(BOLD);
  textSize(42);
  const parts = [[C.text, "Say "], [C.accent, "“clean up my bookmarks”"], [C.text, ". Tidy, in your style."]];
  let total = parts.reduce((w, [, s]) => w + textWidth(s), 0);
  let x = (W - total) / 2;
  noStroke();
  textAlign(LEFT, BASELINE);
  for (const [col, s] of parts) { fill(col); text(s, x, 92); x += textWidth(s); }
  textStyle(NORMAL);
}

function windowFrame() {
  stroke(C.line); strokeWeight(1); fill(C.win);
  rect(80, 128, 1040, 448, 14);
  noStroke();
  [["#ff5f57", 0], ["#febc2e", 1], ["#28c840", 2]].forEach(([c, i]) => { fill(c); circle(106 + i * 22, 152, 13); });
  fill(C.bar); rect(190, 140, 600, 24, 12);
  fill(C.dim); textFont(SANS); textSize(13); textAlign(LEFT, CENTER); text("example.org", 206, 152);
  stroke(C.line); line(80, 176, 1120, 176); line(80, 214, 1120, 214); line(560, 214, 560, 576); noStroke();
}

function bar(t) {
  textFont(SANS); textSize(13); textAlign(LEFT, CENTER);
  let x = 96;
  CHIPS.forEach(([before, after, isFolder], i) => {
    const gone = after === null;
    const shrink = gone ? prog(t, T_COLLAPSE, 0.5) : 0;
    const label = gone ? before : retype(before, after, clamp01((t - T_RETYPE - i * 0.12) / 0.8));
    const shown = fit((isFolder ? "▸ " : "") + label, 230);
    const w = (textWidth(shown) + 26) * (1 - shrink);
    if (w < 2) return;
    const flagged = t > T_FLAG && (gone || before !== after);
    drawingContext.save();
    drawingContext.beginPath(); drawingContext.rect(x, 180, w, 30); drawingContext.clip();
    if (flagged && t < T_COLLAPSE + 0.5) {
      noFill(); stroke(gone ? C.bad : C.accent); strokeWeight(1);
      drawingContext.setLineDash([4, 3]); rect(x + 1, 183, w - 2, 26, 6); drawingContext.setLineDash([]);
    }
    noStroke();
    fill(gone && t > T_STRIKE ? C.dim : before !== after && t > T_RETYPE + 1 ? C.text : C.muted);
    text(shown, x + 13, 196);
    if (gone && t > T_STRIKE) {
      stroke(C.bad); strokeWeight(1.5);
      const sw = textWidth(shown) * prog(t, T_STRIKE, 0.35);
      line(x + 13, 197, x + 13 + sw, 197); noStroke();
    }
    drawingContext.restore();
    x += w + 6 * (1 - shrink);
  });
}

function folder(t) {
  textFont(SANS); textSize(14); textAlign(LEFT, CENTER); noStroke();
  fill(C.dim); textSize(12); text("WORK", 104, 238);
  textSize(14);
  const ROW = 32, TOP = 252;
  // Order after sorting the surviving rows by their new titles.
  const kept = ROWS.map((r, i) => i).filter((i) => ROWS[i][1] !== null);
  const sorted = [...kept].sort((a, b) => ROWS[a][1].toLowerCase() < ROWS[b][1].toLowerCase() ? -1 : 1);
  const collapse = prog(t, T_COLLAPSE, 0.5);
  const sortP = prog(t, T_SORT, 0.9);
  // y before sorting: running sum of (collapsing) heights
  let y = TOP;
  const preY = {};
  ROWS.forEach(([, after], i) => { preY[i] = y; y += after === null ? ROW * (1 - collapse) : ROW; });
  ROWS.forEach(([before, after, dot], i) => {
    const gone = after === null;
    let ry = preY[i];
    if (!gone) ry = lerp(preY[i], TOP + sorted.indexOf(i) * ROW, sortP);
    const h = gone ? ROW * (1 - collapse) : ROW;
    if (h < 1) return;
    drawingContext.save();
    drawingContext.beginPath(); drawingContext.rect(92, ry, 460, h); drawingContext.clip();
    const flagged = t > T_FLAG && t < T_COLLAPSE + 0.5 && (gone || before !== after);
    if (flagged) { fill(gone ? "rgba(224,108,108,0.10)" : "rgba(232,146,90,0.08)"); rect(96, ry + 3, 452, ROW - 6, 6); }
    fill(dot); rect(106, ry + ROW / 2 - 6, 12, 12, 3);
    const label = gone ? before : retype(before, after, clamp01((t - T_RETYPE - i * 0.08) / 0.8));
    const shown = fit(label, 400);
    fill(gone && t > T_STRIKE ? C.dim : !gone && t > T_RETYPE + 1 ? C.text : C.muted);
    text(shown, 130, ry + ROW / 2);
    if (gone && t > T_STRIKE) {
      stroke(C.bad); strokeWeight(1.5);
      line(130, ry + ROW / 2 + 1, 130 + textWidth(shown) * prog(t, T_STRIKE, 0.35), ry + ROW / 2 + 1); noStroke();
    }
    drawingContext.restore();
  });
}

function chat(t) {
  textFont(MONO); textSize(16); textAlign(LEFT, CENTER); noStroke();
  CHAT.forEach((line, i) => {
    if (t < line.at) return;
    const y = 250 + i * 46;
    let x = 590;
    const full = line.parts.map(([, s]) => s).join("");
    const n = line.type ? Math.floor(clamp01((t - line.at) / 1.0) * full.length) : full.length;
    drawingContext.globalAlpha = line.type ? 1 : prog(t, line.at, 0.3);
    let used = 0;
    for (const [col, s] of line.parts) {
      const part = s.slice(0, Math.max(0, n - used));
      used += s.length;
      fill(col); text(part, x, y); x += textWidth(part);
    }
    if (line.type && n < full.length && Math.floor(t * 4) % 2 === 0) { fill(C.text); rect(x + 2, y - 9, 9, 18); }
    drawingContext.globalAlpha = 1;
  });
}

function footer() {
  textFont(SANS); textSize(19); textAlign(LEFT, BASELINE); noStroke();
  const parts = [[C.text, "bookmarkwise", BOLD], [C.muted, " · a Claude Code skill for Chrome bookmarks · ", NORMAL], [C.muted, "github.com/JCPetrelli/bookmarkwise", NORMAL]];
  let total = 0;
  for (const [, s, st] of parts) { textStyle(st); total += textWidth(s); }
  let x = (W - total) / 2;
  for (const [col, s, st] of parts) { textStyle(st); fill(col); text(s, x, 630); x += textWidth(s); }
  textStyle(NORMAL);
}
