// Render the sketch to docs/bookmarkwise.gif, frame by frame, in a headless browser.
//
//   CHROMIUM=/path/to/chromium P5=/path/to/p5.min.js node docs/animation/render.mjs
//
// P5 is optional (default: the CDN copy in index.html). Needs ffmpeg.
import { spawn, execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync, readFileSync, copyFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const HERE = resolve(new URL(".", import.meta.url).pathname);
const OUT = resolve(HERE, "..", process.env.OUT || "bookmarkwise.gif");
const work = mkdtempSync(join(tmpdir(), "bookmarkwise-anim-"));
copyFileSync(join(HERE, "sketch.js"), join(work, "sketch.js"));
let html = readFileSync(join(HERE, "index.html"), "utf-8");
if (process.env.P5) { copyFileSync(process.env.P5, join(work, "p5.min.js")); html = html.replace(/<script src="https:[^"]+p5\.min\.js"><\/script>/, '<script src="p5.min.js"></script>'); }
html = html.replace('<script src="sketch.js"></script>', '<script src="sketch.js"></script><script>window.noLoopAfterSetup=true</script>');
writeFileSync(join(work, "index.html"), html);

const port = 9500 + Math.floor(Math.random() * 300);
const proc = spawn(process.env.CHROMIUM, [`--remote-debugging-port=${port}`, "--headless=new", `--user-data-dir=${join(work, "profile")}`,
  "--allow-file-access-from-files", "--hide-scrollbars", `file://${join(work, "index.html")}`], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let page;
for (let i = 0; i < 50 && !page; i++) {
  await sleep(200);
  try { page = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find((t) => t.type === "page"); } catch {}
}
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const pending = new Map();
ws.onmessage = (e) => { const m = JSON.parse(e.data); if (pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); } };
const send = (method, params) => new Promise((r) => { pending.set(++id, r); ws.send(JSON.stringify({ id, method, params })); });
const evaluate = async (expression) => (await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true })).result.value;

for (let i = 0; i < 50 && !(await evaluate("typeof window.renderFrame === 'function' && !!document.querySelector('canvas')")); i++) await sleep(200);
await evaluate("noLoop()");
const frames = await evaluate("window.FRAMES");
for (let f = 0; f < frames; f++) {
  const url = await evaluate(`window.renderFrame(${f})`);
  writeFileSync(join(work, `f${String(f).padStart(4, "0")}.png`), Buffer.from(url.split(",")[1], "base64"));
}
ws.close(); proc.kill();

const pattern = join(work, "f%04d.png");
execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-framerate", "24", "-i", pattern,
  "-vf", "split[a][b];[a]palettegen=max_colors=64:stats_mode=diff[p];[b][p]paletteuse=dither=none:diff_mode=rectangle",
  "-loop", "0", OUT]);
execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-i", join(work, "f0240.png"), "-vf", "scale=-1:640:flags=lanczos,pad=1280:640:(ow-iw)/2:0:color=0x16171a", resolve(HERE, "..", "social-preview.png")]);  // GitHub social preview size
console.log(`${frames} frames -> ${OUT}`);
