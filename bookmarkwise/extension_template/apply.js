// Bookmarkwise apply page. PLAN comes from plan.js, written by `bookmarkwise build`.
//
// Safeguards, in order:
//  1. Apply is locked until a backup has been downloaded on this page.
//  2. Before anything changes, every target is checked against the snapshot
//     taken when the plan was made. One mismatch and nothing is applied.
//  3. Each op checks its target again right before it runs, and is skipped
//     (never forced) if it no longer matches.
//  4. Folders are only removed when empty. removeTree is never called.
//  5. A plan runs once: this page remembers its hash after applying.
"use strict";

const $ = (sel) => document.querySelector(sel);
const appliedKey = "bookmarkwise-applied-" + PLAN.hash;
const shortHash = PLAN.hash.slice(0, 8);
const state = { backup: false, clean: false, running: false };
const logLines = [];

function log(line) {
  logLines.push(line);
  const el = $("#log");
  el.hidden = false;
  el.textContent = logLines.join("\n");
  el.scrollTop = el.scrollHeight;
}

async function getNode(id) {
  try {
    const [node] = await chrome.bookmarks.get(String(id));
    return node || null;
  } catch (e) {
    return null;
  }
}

function describe(op) {
  const what = op.expect ? JSON.stringify(op.expect.title ?? op.where ?? op.id) : "";
  switch (op.op) {
    case "delete": return `delete ${what}` + (op.reason ? `  (${op.reason})` : "");
    case "update": return `update ${what} -> ` + Object.entries(op.set).map(([k, v]) => `${k} ${JSON.stringify(v)}`).join(", ");
    case "move": return `move ${what} -> ${op.to || op.parent}`;
    case "create_folder": return `new folder ${JSON.stringify(op.title)} in ${op.to || op.parent}`;
    case "create": return `new bookmark ${JSON.stringify(op.title)} in ${op.to || op.parent}`;
    case "sort": return `sort folder ${what}` + (op.folders_first ? " (folders first)" : "");
    case "order": return `restore order of folder ${what}`;
    default: return op.op;
  }
}

// Snapshot of what each target should look like right now. Starts as the
// plan's snapshot and follows the plan's own earlier changes (an update
// before a move of the same bookmark).
const expected = {};
function expectFor(op) {
  if (!expected[op.id]) expected[op.id] = Object.assign({}, op.expect);
  return expected[op.id];
}

function mismatch(node, exp) {
  if (!node) return "bookmark is gone";
  if ("title" in exp && node.title !== exp.title) return `title changed: ${JSON.stringify(exp.title)} -> ${JSON.stringify(node.title)}`;
  if ("url" in exp && node.url !== exp.url) return `URL changed: ${exp.url} -> ${node.url}`;
  if (exp.parent !== undefined && exp.parent !== null && node.parentId !== exp.parent) return "moved to another folder";
  return null;
}

async function preflight() {
  const problems = [];
  for (const [i, op] of PLAN.ops.entries()) {
    if (op.id) {
      const why = mismatch(await getNode(op.id), op.expect);
      if (why) problems.push(`op ${i} (${describe(op)}): ${why}`);
    } else if (op.parent && !op.parent.startsWith("new:")) {
      const parent = await getNode(op.parent);
      if (!parent || parent.url) problems.push(`op ${i} (${op.op}): target folder ${op.parent} is gone`);
    }
  }
  return problems;
}

function compare(foldersFirst) {
  return (a, b) => {
    const fa = foldersFirst && !a.url ? 0 : 1;
    const fb = foldersFirst && !b.url ? 0 : 1;
    if (fa !== fb) return fa - fb;
    const la = a.title.toLowerCase(), lb = b.title.toLowerCase();
    if (la !== lb) return la < lb ? -1 : 1;
    return a.title < b.title ? -1 : a.title > b.title ? 1 : 0;
  };
}

async function clampIndex(parentId, index) {
  if (index === undefined || index === null) return undefined;
  const kids = await chrome.bookmarks.getChildren(parentId);
  return Math.max(0, Math.min(index, kids.length));
}

async function runOp(op, keys) {
  const parentOf = (ref) => (ref.startsWith("new:") ? keys[ref.slice(4)] : ref);

  if (op.op === "create_folder" || op.op === "create") {
    const parentId = parentOf(op.parent);
    if (!parentId) return ["skipped", `its new folder ${op.parent} was not created`];
    const spec = { parentId, title: op.title, index: await clampIndex(parentId, op.index) };
    if (op.op === "create") spec.url = op.url;
    const node = await chrome.bookmarks.create(spec);
    if (op.key) keys[op.key] = node.id;
    return ["done", `${op.op === "create" ? "created" : "new folder"} ${JSON.stringify(op.title)}`];
  }

  const exp = expectFor(op);
  const node = await getNode(op.id);
  const why = mismatch(node, exp);
  const name = JSON.stringify(exp.title ?? (node && node.title) ?? op.id);
  if (why) return ["skipped", `${name}: ${why}`];

  switch (op.op) {
    case "update": {
      await chrome.bookmarks.update(op.id, op.set);
      Object.assign(exp, op.set);
      return ["done", `renamed ${JSON.stringify(op.expect.title)} -> ` + Object.values(op.set).map((v) => JSON.stringify(v)).join(", ")];
    }
    case "move": {
      const parentId = parentOf(op.parent);
      if (!parentId) return ["skipped", `its new folder ${op.parent} was not created`];
      await chrome.bookmarks.move(op.id, { parentId, index: await clampIndex(parentId, op.index) });
      exp.parent = parentId;
      return ["done", `moved ${name}`];
    }
    case "delete": {
      if (!node.url) {
        const kids = await chrome.bookmarks.getChildren(op.id);
        if (kids.length) return ["skipped", `folder ${name} is not empty (${kids.length} items)`];
      }
      await chrome.bookmarks.remove(op.id);
      return ["done", `deleted ${name}`];
    }
    case "sort": {
      const kids = await chrome.bookmarks.getChildren(op.id);
      const sorted = [...kids].sort(compare(op.folders_first));
      for (let i = 0; i < sorted.length; i++) {
        await chrome.bookmarks.move(sorted[i].id, { parentId: op.id, index: i });
      }
      return ["done", `sorted ${name} (${kids.length} items)`];
    }
    case "order": {
      const kids = await chrome.bookmarks.getChildren(op.id);
      const here = new Set(kids.map((k) => k.id));
      const wanted = op.children.map(parentOf).filter((id) => id && here.has(id));
      for (let i = 0; i < wanted.length; i++) {
        await chrome.bookmarks.move(wanted[i], { parentId: op.id, index: i });
      }
      return ["done", `restored order of ${name}`];
    }
    default:
      return ["skipped", `unknown op ${op.op}`];
  }
}

function refreshButtons() {
  const applied = localStorage.getItem(appliedKey);
  $("#apply").disabled = state.running || !!applied || !state.backup || !state.clean;
  if (applied) {
    $("#apply-state").textContent = `This plan was already applied (${JSON.parse(applied).at}). Ask Claude for a new plan.`;
  } else if (!state.backup) {
    $("#apply-state").textContent = "Locked: download the backup first.";
  } else if (!state.clean) {
    $("#apply-state").textContent = "Locked: the check found changes.";
  } else {
    $("#apply-state").textContent = "Ready.";
  }
}

async function runCheck() {
  const box = $("#check-state");
  box.textContent = "Checking…";
  const problems = await preflight();
  state.clean = problems.length === 0;
  if (state.clean) {
    box.innerHTML = `<p class="ok">All ${PLAN.ops.length} operations match your bookmarks.</p>`;
  } else {
    box.innerHTML = `<p class="bad">${problems.length} target(s) changed since the plan was made. Nothing will be applied. Tell Claude, so it can re-read your bookmarks and rebuild the plan.</p>`;
    const ul = document.createElement("ul");
    ul.className = "problems";
    for (const p of problems.slice(0, 50)) {
      const li = document.createElement("li");
      li.textContent = p;
      ul.appendChild(li);
    }
    box.appendChild(ul);
  }
  refreshButtons();
}

async function downloadBackup() {
  const tree = await chrome.bookmarks.getTree();
  const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  const body = JSON.stringify({ bookmarkwise_backup: 1, plan_hash: PLAN.hash, taken: new Date().toISOString(), tree }, null, 1);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([body], { type: "application/json" }));
  a.download = `bookmarkwise-backup-${shortHash}-${stamp}.json`;
  a.click();
  state.backup = true;
  $("#backup-state").textContent = `Saved ${a.download} to your downloads folder.`;
  refreshButtons();
}

async function apply() {
  if (state.running || localStorage.getItem(appliedKey)) return;
  if (!state.backup) return refreshButtons();
  state.running = true;
  refreshButtons();
  // Re-check right before writing: the user may have edited bookmarks since step 2.
  const problems = await preflight();
  if (problems.length) {
    state.running = false;
    state.clean = false;
    await runCheck();
    return;
  }
  log(`Bookmarkwise plan ${shortHash}, ${PLAN.ops.length} operations, ${new Date().toISOString()}`);
  const keys = {};
  let done = 0, skipped = 0, failed = 0;
  for (const [i, op] of PLAN.ops.entries()) {
    try {
      const [status, text] = await runOp(op, keys);
      if (status === "done") done++; else skipped++;
      log(`${String(i).padStart(4)}  ${status.padEnd(7)}  ${text}`);
    } catch (e) {
      failed++;
      log(`${String(i).padStart(4)}  failed   ${describe(op)}: ${e.message}`);
    }
  }
  log(`\napplied ${done}, skipped ${skipped}, failed ${failed}`);
  log("Now tell Claude it is done, so it can check the result.");
  localStorage.setItem(appliedKey, JSON.stringify({ at: new Date().toISOString(), done, skipped, failed }));
  state.running = false;
  $("#download-log").hidden = false;
  refreshButtons();
}

function downloadLog() {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([logLines.join("\n") + "\n"], { type: "text/plain" }));
  a.download = `bookmarkwise-log-${shortHash}.txt`;
  a.click();
}

function init() {
  $("#plan-meta").textContent = `${PLAN.title} · plan ${shortHash} · made ${PLAN.created}`;
  const counts = $("#counts");
  for (const [op, n] of Object.entries(PLAN.counts)) {
    const li = document.createElement("li");
    li.innerHTML = `<b>${n}</b> ${op.replace("_", " ")}`;
    counts.appendChild(li);
  }
  const list = $("#ops");
  for (const op of PLAN.ops) {
    const li = document.createElement("li");
    li.textContent = describe(op);
    list.appendChild(li);
  }
  $("#backup").addEventListener("click", downloadBackup);
  $("#check").addEventListener("click", runCheck);
  $("#apply").addEventListener("click", apply);
  $("#download-log").addEventListener("click", downloadLog);
  refreshButtons();
  runCheck();
}

init();
