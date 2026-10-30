# Bookmarkwise

[![tests](https://github.com/JCPetrelli/bookmarkwise/actions/workflows/test.yml/badge.svg)](https://github.com/JCPetrelli/bookmarkwise/actions/workflows/test.yml) [![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A [Claude Code](https://claude.com/claude-code) skill that cleans up your Chrome bookmarks **in your own style**. Claude asks how you like your bookmarks named, organized and pruned, shows you a plan, and changes nothing until you say yes. The changes then go through Chrome itself, after a backup, so they last and sync like any change you'd make by hand.

![Say "clean up my bookmarks": duplicates and junk links disappear, titles become "Tool · What it is", the folder sorts itself](docs/bookmarkwise.gif)

Every bookmark, folder and URL in this README is invented. The command outputs come from running the tool on the demo profile in [`examples/`](examples/).

- [What it does](#what-it-does)
- [A session with Claude](#a-session-with-claude)
- [Why an extension](#why-an-extension)
- [Safety](#safety)
- [Install](#install)
- [Use it without Claude](#use-it-without-claude)
- [Try it on the demo](#try-it-on-the-demo)
- [Undo](#undo)
- [Limits](#limits)

## What it does

| Step | What happens | You |
|---|---|---|
| 1. Inventory | Reads the profile's bookmark files and finds duplicates, near-duplicates, junk links and messy titles | nothing to do |
| 2. Your style | Asks how you want bookmarks named, which folders to keep, what to remove, what to sort, with your own bookmarks as the examples | answer a few questions, once |
| 3. Plan | Shows tables: what to delete and why, what to rename, what to move, what to sort | approve or change it |
| 4. Extension | Writes a tiny one-off extension that holds only the approved plan | load it, click Backup, click Apply |
| 5. Check | Reads the bookmark files again and confirms every change is there | read the report |

Your answers are saved as a style file (`~/.config/bookmarkwise/style.json`), so the next cleanup starts with one question: "same style as last time?"

What it finds, from the demo profile:

| Finding | Example |
|---|---|
| Exact duplicates | "Harbor API - Confluence", saved twice in the same folder |
| Same page, different decoration | an article saved with and without `?utm_source=newsletter` |
| Pinned page state | a sprint board saved with `?selectedIssue=HAR-311` stuck in the URL |
| Local links | `http://localhost:3000/`, `http://192.168.1.40:8080/admin` |
| Login and redirect links | `…/login?next=%2Fdashboard`, which can point straight at the dashboard |
| Leftovers | `view-source:` links, empty folders, a folder for an archived project |
| Messy titles | "ACME CORP - SPRINT BOARD - Agile Board - Jira", a URL as the title, two bookmarks both called "Board" |
| Kept on purpose | `javascript:` bookmarklets, which are tools rather than pages |

## A session with Claude

You don't need to learn the commands. A session looks roughly like this (an illustration, shortened):

> You: clean up my bookmarks
>
> Claude: You have two Chrome profiles, "Personal" and "Club". Which one?
>
> You: Personal
>
> Claude: 412 bookmarks in 23 folders. 31 are exact duplicates, 12 more differ only by tracking or state parameters, 9 point at localhost or your home network, and about 140 have titles pasted from the page. How would you like them named? Here are three of yours, renamed three ways:
>
> | Now | Tool · What it is | What it is (Tool) | Short |
> |---|---|---|---|
> | ACME CORP - SPRINT BOARD - Agile Board - Jira | Jira · Sprint board | Sprint board (Jira) | Sprint board |
> | Q3 roadmap - Google Sheets | Sheets · Q3 roadmap | Q3 roadmap (Sheets) | Q3 roadmap |
> | https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide | Docs · MDN JavaScript guide | MDN JavaScript guide (Docs) | JavaScript guide |
>
> You: the first one, and keep the bookmarks bar short
>
> Claude: *(a few more questions: folders to protect, what to do with local links, whether to sort)* Here is the plan: 52 deletions, 160 renames, 11 moves, 4 folders sorted. *(tables)* Approve?
>
> You: yes, but keep the localhost ones
>
> Claude: Updated and approved. The extension is in `~/bookmarkwise-work/extension-6d48268b`. Until we're done, please don't change any bookmark, here or on a device that syncs. Load it in `chrome://extensions` (Developer mode → Load unpacked), click its icon, then **Download backup** and **Apply the plan**.
>
> You: done
>
> Claude: All 223 changes are in your bookmarks, nothing skipped. Your bookmarks bar now reads: Mail · Inbox, Jira · Sprint board, Work, Reading.

## Why an extension

Chrome offers three ways to get at bookmarks. Only one of them is good for writing.

| Route | Read | Write | Why |
|---|---|---|---|
| The `Bookmarks` file in the profile folder | ✅ best | ❌ | Chrome rewrites it while running, keeps encrypted copies next to it, and with sync on, edits made behind its back can be undone by the server copy |
| Browser automation on `chrome://bookmarks` | ❌ | ❌ | `chrome://` pages are closed to automation, and clicking through the UI is slow and fragile |
| A one-off **unpacked extension** with the `bookmarks` permission | ✅ | ✅ best | Uses Chrome's own `chrome.bookmarks` API: changes are immediate, sync normally and act on exact bookmark IDs |

So Bookmarkwise reads the file to plan, writes through a tiny extension you load once, then reads the file again to check. The bookmark IDs in the file are the IDs the extension API uses. That joins the two halves. The end-to-end test confirms it in a real browser.

## Safety

- **Nothing changes before your yes.** The inventory and the plan only read. A plan has to be approved before an extension can be built from it. A plan edited after approval won't build.
- **The bookmark files are never written.** Not by the Python tool, not by Claude. All changes go through Chrome.
- **Backup first, enforced.** The extension's Apply button stays locked until you've downloaded a backup of every bookmark in the profile.
- **The freeze window.** From the moment the extension is built until the final check, nobody touches bookmarks: not Claude, and not you. Before it changes anything, the extension checks every bookmark the plan touches: same title, same URL, same folder as when the plan was made. If even one differs, it changes nothing and tells you to rebuild the plan. Each operation is checked again right before it runs.
- **Safe deletes.** A folder is removed only when it's empty. The extension never deletes a folder together with what's inside it.
- **One plan, one run.** After applying, the extension refuses to run the same plan again.
- **Checked afterwards.** Claude reads the bookmark files again and reports every change that's missing.
- **Nothing leaves your computer.** The extension asks for the `bookmarks` permission only. The optional dead-link check is the only thing that uses the network, and it runs only if you agree.

## Install

As a plugin, from inside Claude Code:

```
/plugin marketplace add JCPetrelli/bookmarkwise
/plugin install bookmarkwise@bookmarkwise
```

Or clone the repo and link the skill:

```bash
git clone https://github.com/JCPetrelli/bookmarkwise.git
cd bookmarkwise
just install    # links skills/bookmarkwise into ~/.claude/skills
```

Then say "clean up my bookmarks" in Claude Code. Needs `python3` 3.10 or newer (no packages) and Chrome on macOS, Linux or Windows.

## Use it without Claude

The tool is a plain command line. Claude runs these for you:

```bash
python3 -m bookmarkwise profiles                                       # profiles, names, counts, sync
python3 -m bookmarkwise inventory --profile Default --out inv.json     # read-only findings
python3 -m bookmarkwise freeze draft.json --profile Default --out plan.json
python3 -m bookmarkwise show plan.json                                 # review tables
python3 -m bookmarkwise approve plan.json
python3 -m bookmarkwise check plan.json --profile Default              # drift since freeze
python3 -m bookmarkwise build plan.json --out extension/
python3 -m bookmarkwise verify plan.json --profile Default             # after Apply
```

A draft is a list of operations on bookmark IDs from the inventory:

```json
{"title": "Bookmarks cleanup", "ops": [
  {"op": "delete", "id": "9", "reason": "exact duplicate"},
  {"op": "update", "id": "5", "title": "Jira (Acme) · Sprint board"},
  {"op": "create_folder", "key": "docs", "parent": "2", "title": "Docs"},
  {"op": "move", "id": "24", "parent": "new:docs"},
  {"op": "sort", "id": "7", "folders_first": true}
]}
```

`freeze` refuses a draft that touches the root folders, deletes a folder that would still hold bookmarks, or has two operations fighting over one bookmark.

## Try it on the demo

[`examples/demo/Bookmarks`](examples/demo/Bookmarks) is an invented profile with 25 bookmarks and every kind of mess listed above. [`examples/demo-draft.json`](examples/demo-draft.json) is a cleanup plan for it. [`examples/walkthrough.txt`](examples/walkthrough.txt) is the real output of `just demo`, from the inventory to the built extension:

```
$ bw freeze examples/demo-draft.json --bookmarks examples/demo/Bookmarks --out <work>/plan.json
frozen 28 operations (1 create_folder, 15 update, 2 move, 9 delete, 1 sort) -> <work>/plan.json

$ bw build <work>/plan.json --out <work>/extension
the plan is not approved: show it to the user, then run `approve` after their yes
```

The end-to-end test (`CHROMIUM=/path/to/chromium just e2e`) runs that plan in a real browser with a throwaway profile. It checks that a drifted plan is refused with nothing changed, that all 28 operations apply, that the bookmarks file shows them, and that the undo restores the original titles, URLs and order.

## Undo

The backup the extension downloads is the way back. Claude turns it into an undo plan: it re-creates deleted bookmarks and folders, restores old titles and URLs, moves bookmarks back, removes folders the plan created and restores the original order. The undo goes through the same review, extension and check as any plan.

```bash
python3 -m bookmarkwise undo plan.json --backup bookmarkwise-backup-6d48268b-….json --profile Default --out undo-draft.json
```

Re-created bookmarks get new IDs, so anything that pointed at the old ones (another device's open tab, say) won't follow them.

## Limits

- **Chrome first.** Tested with Chrome for Testing 156 on macOS, and on Linux in CI. Brave, Edge, Vivaldi and Chromium keep the same files and API (`--browser brave`), but they aren't tested.
- **Bookmarks saved to your Google account** live in a second file, `AccountBookmarks`, which Bookmarkwise reads as well. Their IDs are checked the same way, so if Chrome ever showed them differently, the extension would refuse rather than change the wrong bookmark.
- **Loading the extension is a manual step.** Chrome lets only you add an unpacked extension (Developer mode → Load unpacked). Remove it when you're done.
- **The plain file must be current.** Recent Chrome keeps an encrypted copy (`EncryptedBookmarks2`) next to the plain one. If the plain one looks older, the inventory warns you and Claude stops.
- **Dead links are opt-in.** `bookmarkwise links` asks each site once. Some sites block automated requests, so "check" results need a human look.

Chrome™ is a trademark of Google LLC. Use of this trademark is subject to Google Permissions. Bookmarkwise is not affiliated with or endorsed by Google.

## License

[MIT](LICENSE)
