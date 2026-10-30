// End-to-end test in a real Chromium with a throwaway profile (never your own browser).
//
//   CHROMIUM=/path/to/chromium node tests/e2e/run.mjs
//
// Seeds the demo Bookmarks file, freezes/approves/builds the demo plan, loads
// the extension, clicks Backup and Apply on its page, closes the browser and
// verifies the Bookmarks file. Then it checks that a drifted plan is refused
// with nothing changed, and that the undo plan restores the original tree.
// Branded Google Chrome ignores --load-extension; use Chromium or Chrome for Testing.

import { spawn, execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, copyFileSync, readFileSync, readdirSync, writeFileSync, existsSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { createHash, generateKeyPairSync } from "node:crypto";
import { join, resolve } from "node:path";

const ROOT = resolve(new URL("../..", import.meta.url).pathname);
const CHROMIUM = process.env.CHROMIUM;
if (!CHROMIUM || !existsSync(CHROMIUM)) {
  console.error("set CHROMIUM to a Chromium or Chrome for Testing binary");
  process.exit(2);
}
const work = mkdtempSync(join(tmpdir(), "bookmarkwise-e2e-"));
const profile = join(work, "profile");
const downloads = join(work, "downloads");
mkdirSync(join(profile, "Default"), { recursive: true });
mkdirSync(downloads);
const bookmarksFile = join(profile, "Default", "Bookmarks");
// Recent Chrome versions also keep EncryptedBookmarks2 (and .bak copies) and prefer them
// on start-up, so a re-seed removes every copy the browser wrote.
function seed() {
  for (const f of readdirSync(join(profile, "Default"))) {
    if (/Bookmarks/.test(f)) rmSync(join(profile, "Default", f), { force: true });
  }
  copyFileSync(join(ROOT, "examples", "demo", "Bookmarks"), bookmarksFile);
}
seed();

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const bw = (...args) => execFileSync("python3", ["-m", "bookmarkwise", ...args], { cwd: ROOT, encoding: "utf-8" });
const bwStatus = (...args) => {
  try { bw(...args); return 0; } catch (e) { return e.status; }
};
let failures = 0;
const check = (ok, label) => { console.log(`${ok ? "PASS" : "FAIL"}  ${label}`); if (!ok) failures++; };

function shape(file) {
  // Titles, URLs and nesting, without ids or dates: what the user sees.
  const data = JSON.parse(readFileSync(file, "utf-8"));
  // Root names are left out: browsers spell them differently ("Bookmarks bar" / "Bookmarks Bar").
  const walk = (n) => (n.type === "url" ? [n.name, n.url] : [n.name, (n.children || []).map(walk)]);
  return JSON.stringify(["bookmark_bar", "other", "synced"].map((k) => (data.roots[k].children || []).map(walk)));
}

// Give the test copy of the extension a manifest "key", so its id is known in advance
// (Chrome derives it from the key: sha256 of the public key, first 32 hex digits mapped 0-f -> a-p).
function pinId(extDir) {
  const { publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
  const der = publicKey.export({ type: "spki", format: "der" });
  const manifestPath = join(extDir, "manifest.json");
  const manifest = JSON.parse(readFileSync(manifestPath, "utf-8"));
  manifest.key = der.toString("base64");
  writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));
  return [...createHash("sha256").update(der).digest("hex").slice(0, 32)].map((c) => String.fromCharCode(97 + parseInt(c, 16))).join("");
}

async function withBrowser(extDir, fn) {
  const wanted = [pinId(extDir)];
  const port = 9300 + Math.floor(Math.random() * 500);
  const proc = spawn(CHROMIUM, [
    `--user-data-dir=${profile}`, `--remote-debugging-port=${port}`, "--headless=new",
    "--no-first-run", "--no-default-browser-check", "--disable-sync",
    ...(process.platform === "linux" ? ["--no-sandbox", "--disable-dev-shm-usage"] : []),
    `--disable-extensions-except=${extDir}`, `--load-extension=${extDir}`, "about:blank",
  ], { stdio: "ignore" });
  try {
    let targets = [];
    for (let i = 0; i < 150; i++) {
      await sleep(200);
      try {
        targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
        if (targets.some((t) => wanted.some((id) => t.url.startsWith(`chrome-extension://${id}/`)))) break;
      } catch {}
    }
    // Our service worker, not one of the browser's built-in component extensions.
    const sw = targets.find((t) => wanted.some((id) => t.url.startsWith(`chrome-extension://${id}/`)));
    if (!sw) throw new Error(`extension ${wanted[0]} did not load; targets:\n  ` + targets.map((t) => `${t.type} ${t.url}`).join("\n  "));
    const extId = new URL(sw.url).host;
    const version = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
    const browser = await cdp(version.webSocketDebuggerUrl);
    await browser.send("Browser.setDownloadBehavior", { behavior: "allow", downloadPath: downloads });
    const page = await (await fetch(`http://127.0.0.1:${port}/json/new?chrome-extension://${extId}/apply.html`, { method: "PUT" })).json();
    const tab = await cdp(page.webSocketDebuggerUrl);
    const evaluate = async (expr) => {
      const r = await tab.send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
      if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
      return r.result.value;
    };
    for (let i = 0; i < 50; i++) {
      await sleep(200);
      if ((await evaluate("location.href")).startsWith("chrome-error:")) {
        // The page was opened before the extension finished registering: open it again.
        await tab.send("Page.navigate", { url: `chrome-extension://${extId}/apply.html` });
        continue;
      }
      const text = await evaluate(`document.querySelector('#check-state')?.textContent || ''`).catch(() => "");
      if (text && !text.startsWith("Checking")) break;
    }
    await fn(evaluate);
    tab.close();
    await browser.send("Browser.close").catch(() => {});
    browser.close();
  } finally {
    for (let i = 0; i < 50 && proc.exitCode === null; i++) await sleep(100);
    if (proc.exitCode === null) proc.kill();
    await sleep(300);
  }
}

function cdp(url) {
  return new Promise((resolveConn, reject) => {
    const ws = new WebSocket(url);
    let id = 0;
    const pending = new Map();
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.id && pending.has(msg.id)) {
        const { res, rej } = pending.get(msg.id);
        pending.delete(msg.id);
        msg.error ? rej(new Error(msg.error.message)) : res(msg.result);
      }
    };
    ws.onerror = reject;
    ws.onopen = () => resolveConn({
      send: (method, params = {}) => new Promise((res, rej) => { const i = ++id; pending.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method, params })); }),
      close: () => ws.close(),
    });
  });
}

async function applyPlan(evaluate) {
  const locked = await evaluate(`document.querySelector('#apply').disabled`);
  await evaluate(`document.querySelector('#backup').click()`);
  await sleep(500);
  const unlocked = await evaluate(`!document.querySelector('#apply').disabled`);
  await evaluate(`document.querySelector('#apply').click()`);
  for (let i = 0; i < 50; i++) {
    await sleep(200);
    if (await evaluate(`document.querySelector('#log').textContent.includes('applied ')`)) break;
  }
  const log = await evaluate(`document.querySelector('#log').textContent`);
  const lockedAfter = await evaluate(`document.querySelector('#apply').disabled`);
  return { locked, unlocked, log, lockedAfter };
}

const original = shape(bookmarksFile);
const plan = join(work, "plan.json");
const ext = join(work, "ext");
bw("freeze", "examples/demo-draft.json", "--bookmarks", bookmarksFile, "--out", plan);
check(bwStatus("build", plan, "--out", ext) !== 0, "build refuses an unapproved plan");
bw("approve", plan);
bw("build", plan, "--out", ext);

// 1. A drifted plan: rename one target in the file first; the page must refuse and change nothing.
const drifted = JSON.parse(readFileSync(bookmarksFile, "utf-8"));
drifted.roots.bookmark_bar.children[0].name = "Renamed by hand";
seed();
writeFileSync(bookmarksFile, JSON.stringify(drifted, null, 3));
const driftedShape = shape(bookmarksFile);
check(bwStatus("check", plan, "--bookmarks", bookmarksFile) === 1, "check reports drift");
await withBrowser(ext, async (evaluate) => {
  await evaluate(`document.querySelector('#backup').click()`);
  await sleep(500);
  const disabled = await evaluate(`document.querySelector('#apply').disabled`);
  const text = await evaluate(`document.querySelector('#check-state').textContent`);
  check(disabled && text.includes("Nothing will be applied"), "page locks Apply when a target drifted");
});
check(shape(bookmarksFile) === driftedShape, "drifted run changed nothing");

// 2. The real run, on the untouched demo.
seed();
await withBrowser(ext, async (evaluate) => {
  const r = await applyPlan(evaluate);
  check(r.locked, "Apply is locked before the backup");
  check(r.unlocked, "Apply unlocks after backup + clean check");
  check(/applied 28, skipped 0, failed 0/.test(r.log), "all 28 operations applied");
  check(r.lockedAfter, "Apply locks after running once");
});
check(bwStatus("verify", plan, "--bookmarks", bookmarksFile) === 0, "verify finds every change in the Bookmarks file");
const after = model(bookmarksFile);
check(after.includes("Jira (Acme) · Board (filter 12)") && !after.includes("view-source:"), "file shows renames and deletes");

// 3. Undo from the downloaded backup.
const backups = readdirSync(downloads).filter((f) => f.startsWith("bookmarkwise-backup-"));
check(backups.length >= 1, "backup file was downloaded");
const undoDraft = join(work, "undo-draft.json");
const undoPlan = join(work, "undo.json");
const undoExt = join(work, "undo-ext");
bw("undo", plan, "--backup", join(downloads, backups.at(-1)), "--bookmarks", bookmarksFile, "--out", undoDraft);
bw("freeze", undoDraft, "--bookmarks", bookmarksFile, "--out", undoPlan);
bw("approve", undoPlan);
bw("build", undoPlan, "--out", undoExt);
await withBrowser(undoExt, async (evaluate) => {
  const r = await applyPlan(evaluate);
  const clean = /skipped 0, failed 0/.test(r.log);
  check(clean, "undo plan applied without skips");
  if (!clean) console.log(r.log.split("\n").filter((l) => !/ done /.test(l)).join("\n"));
});
check(shape(bookmarksFile) === original, "undo restores the original titles, URLs and order");

function model(file) { return readFileSync(file, "utf-8"); }

console.log(failures ? `\n${failures} failed (work dir ${work})` : "\nall e2e checks passed");
process.exit(failures ? 1 : 0);
