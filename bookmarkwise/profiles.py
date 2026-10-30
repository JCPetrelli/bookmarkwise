"""Find browser profiles that have a Bookmarks file.

Chrome is the target. Other Chromium browsers keep the same file and the same
extension API, so they are listed too, but they are not tested.
"""

from __future__ import annotations

import json
import os
import platform
from pathlib import Path

from . import model

# browser key -> (label, macOS dir, Linux dir, Windows dir under LOCALAPPDATA)
BROWSERS = {
    "chrome": ("Google Chrome", "Google/Chrome", "google-chrome", r"Google\Chrome\User Data"),
    "chrome-beta": ("Google Chrome Beta", "Google/Chrome Beta", "google-chrome-beta", r"Google\Chrome Beta\User Data"),
    "chromium": ("Chromium", "Chromium", "chromium", r"Chromium\User Data"),
    "brave": ("Brave", "BraveSoftware/Brave-Browser", "BraveSoftware/Brave-Browser", r"BraveSoftware\Brave-Browser\User Data"),
    "edge": ("Microsoft Edge", "Microsoft Edge", "microsoft-edge", r"Microsoft\Edge\User Data"),
    "vivaldi": ("Vivaldi", "Vivaldi", "vivaldi", r"Vivaldi\User Data"),
}


def user_data_dir(browser: str, system: str | None = None, home: Path | None = None) -> Path:
    label, mac, linux, win = BROWSERS[browser]
    system = system or platform.system()
    home = home or Path.home()
    if system == "Darwin":
        return home / "Library" / "Application Support" / mac
    if system == "Windows":
        base = os.environ.get("LOCALAPPDATA") or str(home / "AppData" / "Local")
        return Path(base) / win
    return home / ".config" / linux


def profile_names(data_dir: Path) -> dict[str, str]:
    """Profile folder -> display name, from the `Local State` file."""
    try:
        state = json.loads((data_dir / "Local State").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    cache = state.get("profile", {}).get("info_cache", {})
    return {folder: info.get("name", folder) for folder, info in cache.items()}


def find(browsers: list[str] | None = None, home: Path | None = None, system: str | None = None) -> list[dict]:
    found = []
    for key in browsers or list(BROWSERS):
        data_dir = user_data_dir(key, system=system, home=home)
        if not data_dir.is_dir():
            continue
        names = profile_names(data_dir)
        for sub in sorted(data_dir.iterdir()):
            bm = sub / model.LOCAL_FILE
            acct = sub / model.ACCOUNT_FILE
            if not bm.is_file() and not acct.is_file():
                continue
            try:
                tree = model.load(sub)
                count = len(tree.bookmarks())
                sync_on = tree.sync_on
            except (OSError, ValueError, KeyError):
                count, sync_on = None, None
            found.append({
                "browser": key,
                "browser_name": BROWSERS[key][0],
                "profile_dir": sub.name,
                "profile_name": names.get(sub.name, sub.name),
                "bookmarks_file": str(bm if bm.is_file() else acct),
                "files": [f.name for f in (bm, acct) if f.is_file()],
                "bookmarks": count,
                "sync_on": sync_on,
            })
    return found
