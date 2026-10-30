# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

A Claude Code skill plus its engine, for public release (MIT). The skill is `skills/bookmarkwise/SKILL.md`, distributed as a plugin (`.claude-plugin/`) or by symlink with `just install`. The skill finds the engine two directories above its base directory: never hardcode machine paths in it.

- `bookmarkwise/` is a stdlib-only Python package. It **only reads** the browser's `Bookmarks` / `AccountBookmarks` files. Nothing in it may ever write them.
- `bookmarkwise/extension_template/` is the one-off Manifest V3 extension. `apply.js` is the only code that changes bookmarks, through `chrome.bookmarks`, after a backup, with a full drift check first and a per-op check after.
- `tests/helpers.py` has `simulate`, a Python stand-in for `apply.js`. Change both together, and run the e2e test after any change to `apply.js`.

## Commands

```bash
just test          # unit tests, no browser
just demo          # regenerate examples/walkthrough.txt (CI fails if it is stale)
CHROMIUM=... just e2e   # real browser, throwaway profile: apply, drift refusal, undo
CHROMIUM=... just gif   # re-render docs/bookmarkwise.gif from docs/animation/sketch.js
```

Branded Google Chrome ignores `--load-extension`: e2e needs Chromium or Chrome for Testing (gif works with any headless Chromium).

## Rules

- Every bookmark, folder and URL in the repo is invented (Acme Corp, the Harbor project, example.org). Keep it that way.
- New op kinds need: freeze validation (`plan.py`), the extension (`apply.js`), the simulator (`tests/helpers.py`), verify, undo, and a line in SKILL.md.
