---
name: bookmarkwise
description: Use when the user wants to clean up, tidy, organize, deduplicate, rename or relabel their Chrome bookmarks (or another Chromium browser's — Brave, Edge, Vivaldi) — duplicate bookmarks, dead or localhost links, pasted-in page titles, near-twin bookmarks they can't tell apart, a messy bookmarks bar, folders to reorganize. Triggers on "clean up my bookmarks", "organize my Chrome bookmarks", "rename my bookmarks", "dedupe bookmarks", "my bookmarks bar is a mess", "/bookmarkwise".
---

# Bookmarkwise

Clean up a user's browser bookmarks in **their** style, safely. The method:

1. **Read** the profile's `Bookmarks` file (and `AccountBookmarks`, if there is one) to plan. Never write to these files.
2. **Ask** how the user wants their bookmarks named, organized and cleaned, and save the answers as their style.
3. **Propose** a plan as review tables. Change nothing until the user approves.
4. **Write** the approved plan into a tiny one-off extension that uses the browser's own `chrome.bookmarks` API. The user loads it and clicks Backup, then Apply. Changes sync normally.
5. **Verify** by reading the file again.

Bookmark IDs in the file are the IDs the extension API uses. That joins the read side to the write side.

## Setup

The engine is two directories above this skill's base directory. Shell variables don't survive between tool calls, so start every command with the full prefix:

```bash
PYTHONPATH="<skill base directory>/../.." python3 -m bookmarkwise --help
```

Below, `bw` stands for that prefix. Needs `python3` 3.10+, no packages. Ask the user for a **working folder** for inventories, plans and the extension (default: `~/bookmarkwise-work`). These files list their bookmarks: keep them out of git repos and shared folders.

## Rules (read these first)

- **Read-only until approval.** Before the user says yes to a plan, nothing changes: not the files, not the browser.
- **Never write the Bookmarks file** (or `AccountBookmarks`, or any `Encrypted*`/`.bak` copy). The browser rewrites them while running, and sync can undo edits made behind its back.
- **Don't try the blocked routes.** Don't script `chrome://bookmarks`. Don't click through the browser with screen control. Don't drive the user's browser with automation tools. Use the extension. If the user asks for another route, explain why the extension is the safe one.
- **Act on IDs, with a snapshot.** Never match bookmarks by title alone. `freeze` records every target's title, URL and folder. The extension refuses to apply if any of them changed.
- **The freeze window.** From the moment the extension is built until verify has run, nobody changes bookmarks: not you, and not the user. Tell the user this in plain words when you hand over (template below). If they need to change something, they say so, and you start again from a fresh inventory and a new plan. Never "adjust" a built plan: rebuild it.
- **Backup before Apply.** The extension enforces it: Apply stays locked until the backup has been downloaded.
- **One plan, one run.** A plan applies once. For more changes, make a new plan from a fresh inventory.
- **Nothing leaves the machine.** Don't upload bookmarks, inventories or plans, and don't paste them into web services. The dead-link check (`bw links`) contacts each bookmarked site. Run it only after the user says yes to that.
- **Ask, don't guess.** A stale-looking link, a folder that might matter, an unclear abbreviation: ask. Anything unsure goes in a "Maybe" list and is kept by default.
- **Never invent a URL.** A repaired URL must come from the bookmark itself (the page a login redirect points to, the same page without tracking parameters) or from the user.

## Workflow

### 1. Find the profile

`bw profiles` lists every profile with a Bookmarks file: browser, folder, the name the user sees, bookmark count, and whether sync is on. More than one profile: ask which one (show the names, not the folder names). In recent Chrome, bookmarks saved to the Google account live in `AccountBookmarks`. `bw` reads both files and marks the account folders "(account)".

If `inventory` prints a **WARNING** that the plain file looks stale, stop. Ask the user to make one small change in the browser (star and unstar any page), then run inventory again.

### 2. Inventory (read-only)

`bw inventory --profile "<name>" --out <work>/inventory.json` prints counts and findings: exact and near duplicates, flagged URLs (`local`, `login-redirect`, `redirect`, `view-source`, `browser-internal`, `edit-or-draft`, `pinned-state`, `tracking-params`, `bookmarklet`), title issues (`site-suffix`, `title-is-url`, `long`, `all-caps`, `no-title`) and empty folders. Read the JSON to see the folder list, the top domains and every bookmark with its ID.

Tell the user what you found in two or three plain lines (counts, the biggest problems). Don't dump the table.

### 3. Learn the user's style

Check for a saved style first: `bw style show` (default `~/.config/bookmarkwise/style.json`). If there is one, summarize it in three lines and ask "keep this style, or change something?". Skip to step 4 if they keep it.

Otherwise, interview. Use `AskUserQuestion`, a few questions at a time, and **build every option from the user's own bookmarks**: show what three of their real bookmarks would become under each choice (in the option `preview`). Recommend the option that fits what you saw. Cover:

1. **Naming.** Show 3 of their messiest titles renamed in 3 ways. For example:
   - `Tool · What it is`: "ACME - SPRINT BOARD - Agile Board - Jira" → `Jira · Sprint board`
   - `What it is (Tool)` → `Sprint board (Jira)`
   - Short, plain → `Sprint board`
   - Keep titles, fix only the broken ones (URL as title, no title, ALL CAPS)

   Follow up only where it matters: the separator (`·`, `-`, `|`, `:`), the prefixes they use (`Jira`, `Docs`, `Article`, `Env`…), how to tell twin instances apart (`Jira (Work)` / `Jira (Club)`), the title language, and a length limit.
2. **The bookmarks bar.** Short titles, or icons only (empty titles: the favicon alone shows)? Which bookmarks belong on the bar at all?
3. **Folders.** Keep their folders as they are, tidy inside them, or reorganize: by topic, by tool, or by project/area of life. If they want to reorganize, propose a folder tree from their top domains and folders, and let them edit it. Ask which folders are **protected** (never touched).
4. **What to remove.** Go through the finding kinds they actually have, with counts and one real example each: exact duplicates (which copy to keep), near duplicates, localhost/LAN links, login and redirect links, view-source and browser-internal links, edit/draft links, empty folders, and things they've archived or replaced ("old job", "finished projects"). Bookmarklets (`javascript:`) are tools: keep them unless they say otherwise.
5. **Repairs.** Strip tracking parameters? Follow login redirects to the real page? Check for dead links (uses the network; their choice)?
6. **Order.** Sort folders alphabetically (with the `Tool ·` pattern this groups each tool's links)? Folders first? Which folders keep their hand-made order (the bar usually does)?

Save the answers: `bw style init` writes a template. Fill it in from the answers (in `naming.examples`, keep two or three before → after pairs they approved). Show the file's path. Next time, step 3 is one question.

### 4. Draft the plan

Write a draft JSON in the working folder. Ops use the IDs from the inventory:

```json
{"title": "Bookmarks cleanup", "ops": [
  {"op": "delete", "id": "42", "reason": "exact duplicate of 'Docs · Python 3' in Reading"},
  {"op": "update", "id": "57", "title": "Jira (Work) · Sprint board", "reason": "pasted page title"},
  {"op": "update", "id": "61", "url": "https://admin.example.org/dashboard", "title": "Env · Admin", "reason": "login redirect -> its target"},
  {"op": "create_folder", "key": "docs", "parent": "2", "title": "Docs", "index": 0},
  {"op": "move", "id": "63", "parent": "new:docs"},
  {"op": "delete", "id": "70", "reason": "empty folder"},
  {"op": "sort", "id": "7", "folders_first": true}
]}
```

- Every delete has a one-line `reason`.
- A folder can only be deleted if the same plan deletes or moves out everything in it.
- Root folders (Bookmarks bar, Other bookmarks, Mobile bookmarks) can be sorted and used as parents, never renamed, moved or deleted.
- Leave protected folders alone, and keep the "Maybe" items out of the plan.
- Big collections: one plan per area (the bar first, then one folder tree at a time) keeps each review short. Run a fresh inventory before each new plan.

Freeze it: `bw freeze draft.json --profile "<name>" --out <work>/plan.json`. If freeze refuses, fix the draft. Never edit `plan.json` by hand.

### 5. Review and approval

`bw show plan.json` prints the review tables: Delete, Rename (update), Move, New folders, Sort. Show them to the user, 40 rows at a time for long lists, with the "Maybe" list after them. Wait for an explicit yes. Changes go back into the draft. Freeze again and show the new tables.

After the yes, `bw approve plan.json`. Approval records the plan's hash. A plan edited after approval won't build.

### 6. Build the extension

`bw check plan.json --profile "<name>"` must say "no drift". Then `bw build plan.json --out <work>/extension-<hash8>`.

### 7. Hand over (the freeze window starts)

Say this, adapted to the user's browser and language:

> The extension is ready in `<folder>`. Until we're done, please don't add, rename, move or delete any bookmark, on this computer or any device that syncs with it. The extension checks every bookmark it touches, and if anything changed, it stops without changing anything.
>
> 1. Open `chrome://extensions` and turn on **Developer mode** (top right).
> 2. Click **Load unpacked** and pick the folder `<folder>`.
> 3. Click the puzzle-piece icon, then **Bookmarkwise apply**. A page opens.
> 4. Click **Download backup**, then **Apply the plan**.
> 5. Tell me when the log says "applied".

Then wait. Don't run any command that changes anything while you wait.

If the page says targets changed: nothing was applied. Run a fresh inventory, rebuild the plan from the same decisions (IDs that are gone drop out), show only what differs, approve again, build a new extension.

### 8. Verify

`bw verify plan.json --profile "<name>"` reads the file again (the browser writes it within seconds) and lists every operation not found. If an operation is missing, read the extension's log (the user can download it) to find out why: skipped because it changed, a folder not empty, or the file not written yet (wait a few seconds and run verify again). Report the result: applied, skipped and why, and show the bar's or the main folder's new contents. Don't report success before verify passes.

### 9. Clean up

Ask the user to remove the extension (`chrome://extensions` → Remove) and delete its folder. They keep the backup JSON until they're happy with the result.

## Undo

`bw undo plan.json --backup <bookmarkwise-backup-….json> --profile "<name>" --out undo-draft.json` writes an undo draft. It re-creates deleted bookmarks and folders, restores old titles and URLs, moves bookmarks back, removes the folders the plan created and restores the original order. Then treat it like any plan: freeze, show, approve, check, build, hand over, verify. Re-created bookmarks get new IDs.

## Commands

| Command | Does |
|---|---|
| `bw profiles` | profiles with bookmarks, names, counts, sync |
| `bw inventory --profile P --out inv.json` | read-only findings |
| `bw style init\|show\|check [--style F]` | the saved style |
| `bw freeze draft.json --profile P --out plan.json` | snapshot + validate |
| `bw show plan.json [--limit N]` | review tables |
| `bw approve plan.json` | only after the user's yes |
| `bw check plan.json --profile P` | drift since freeze |
| `bw build plan.json --out DIR` | the one-off extension |
| `bw verify plan.json --profile P [--all]` | did every change land |
| `bw undo plan.json --backup B --profile P --out undo.json` | reverse a plan |
| `bw links --inventory inv.json --out links.json` | dead links (network, opt-in) |

`--bookmarks PATH` works instead of `--profile` for any Bookmarks file, and `--browser brave|edge|chromium|vivaldi|chrome-beta` picks another browser (default `chrome`).
