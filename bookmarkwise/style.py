"""The user's bookmark style: the answers to the interview, saved for next time.

The file is plain JSON so the user can read and edit it. Claude fills it in
from the interview in SKILL.md and reads it before drafting every plan.
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_PATH = Path("~/.config/bookmarkwise/style.json")

TEMPLATE = {
    "bookmarkwise_style": 1,
    "naming": {
        "pattern": "Tool · What it is",
        "separator": " · ",
        "prefixes": [],
        "instance_in_brackets": True,
        "case": "as-is",
        "max_length": 50,
        "bar_titles": "short",
        "language": "keep each title's language",
        "examples": [],
    },
    "structure": {
        "approach": "keep my folders",
        "folders": [],
        "protected_folders": [],
        "max_depth": 3,
    },
    "cleanup": {
        "exact_duplicates": "delete, keep the one in the most specific folder",
        "near_duplicates": "ask",
        "local_links": "ask",
        "login_and_redirect_links": "repair to the real page when obvious, else ask",
        "view_source_and_browser_internal": "delete",
        "edit_and_draft_links": "ask",
        "tracking_parameters": "strip",
        "empty_folders": "delete",
        "bookmarklets": "keep",
        "dead_link_check": "off",
    },
    "sorting": {
        "folders_to_sort": [],
        "folders_first": True,
        "leave_order": ["Bookmarks bar"],
    },
    "notes": [],
}

REQUIRED = ("naming", "structure", "cleanup", "sorting")


def path(p: str | None) -> Path:
    return Path(p).expanduser() if p else DEFAULT_PATH.expanduser()


def init(p: str | None, force: bool = False) -> Path:
    target = path(p)
    if target.exists() and not force:
        raise FileExistsError(f"{target} already exists (pass --force to start over)")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(TEMPLATE, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def load(p: str | None) -> dict:
    return json.loads(path(p).read_text(encoding="utf-8"))


def problems(style: dict) -> list[str]:
    out = []
    if style.get("bookmarkwise_style") != 1:
        out.append("missing 'bookmarkwise_style': 1")
    for key in REQUIRED:
        if not isinstance(style.get(key), dict):
            out.append(f"missing section '{key}'")
    return out
