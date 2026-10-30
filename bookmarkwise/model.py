"""Read a Chromium `Bookmarks` file into flat, easy-to-check records.

This module only reads. Nothing in Bookmarkwise ever writes the Bookmarks
file: the browser rewrites it while running, and sync can undo edits made
behind its back. Changes go through the one-off extension instead.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

# Top-level containers in the file. They can hold bookmarks but can never be
# renamed, moved or deleted, through the API or otherwise.
ROOT_KEYS = ("bookmark_bar", "other", "synced")
ROOT_LABELS = {
    "bookmark_bar": "Bookmarks bar",
    "other": "Other bookmarks",
    "synced": "Mobile bookmarks",
}


@dataclass
class Node:
    id: str
    type: str  # "url" or "folder"
    title: str
    url: str | None
    parent_id: str | None
    index: int
    path: list[str] = field(default_factory=list)  # folder titles from the root down, excluding self
    root: str = ""
    children: list[str] = field(default_factory=list)
    date_added: str | None = None
    date_last_used: str | None = None

    @property
    def is_folder(self) -> bool:
        return self.type == "folder"

    @property
    def is_root(self) -> bool:
        return self.parent_id is None

    @property
    def location(self) -> str:
        return " / ".join(self.path) if self.path else "(root)"

    def snapshot(self) -> dict:
        """What the extension compares against before it changes this node.

        Root folders carry no title: the file and the API spell their names
        differently, and they can never be renamed anyway.
        """
        if self.is_root:
            return {}
        snap = {"title": self.title}
        if self.url is not None:
            snap["url"] = self.url
        return snap

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "path": self.location,
            "parent_id": self.parent_id,
            "index": self.index,
        }
        if self.url is not None:
            d["url"] = self.url
        if self.is_folder:
            d["children"] = len(self.children)
        return d


class Tree:
    def __init__(self, nodes: dict[str, Node], roots: dict[str, str], sync_on: bool, sha256: str, path: Path | None):
        self.nodes = nodes
        self.roots = roots  # root key -> node id ("account:bookmark_bar" for account bookmarks)
        self.sync_on = sync_on
        self.sha256 = sha256
        self.path = path
        self.files: list[str] = [str(path)] if path else []
        self.warnings: list[str] = []

    def __getitem__(self, node_id: str) -> Node:
        return self.nodes[node_id]

    def __contains__(self, node_id: str) -> bool:
        return node_id in self.nodes

    def bookmarks(self) -> list[Node]:
        return [n for n in self.nodes.values() if n.type == "url"]

    def folders(self, include_roots: bool = False) -> list[Node]:
        return [n for n in self.nodes.values() if n.is_folder and (include_roots or not n.is_root)]

    def descendants(self, node_id: str) -> list[Node]:
        out: list[Node] = []
        stack = list(reversed(self.nodes[node_id].children))
        while stack:
            child = self.nodes[stack.pop()]
            out.append(child)
            stack.extend(reversed(child.children))
        return out


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


LOCAL_FILE = "Bookmarks"
# Chrome 13x+ keeps bookmarks saved to the Google account in a second file. The
# extension API shows both sets together, with ids that do not collide.
ACCOUNT_FILE = "AccountBookmarks"
ACCOUNT_SUFFIX = " (account)"


def _read(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()


def load(path: str | Path, with_account: bool = True) -> Tree:
    """Load a Bookmarks file, plus the AccountBookmarks file next to it when there is one."""
    path = Path(path).expanduser()
    if path.is_dir():
        local, account = path / LOCAL_FILE, path / ACCOUNT_FILE
    elif path.name == ACCOUNT_FILE:
        local, account = path.with_name(LOCAL_FILE), path
    else:
        local, account = path, path.with_name(ACCOUNT_FILE)
    sources = [(f, "") for f in (local,) if f.is_file()]
    if with_account and account.is_file() and account != local:
        sources.append((account, ACCOUNT_SUFFIX))
    if not sources:
        raise FileNotFoundError(f"no {LOCAL_FILE} or {ACCOUNT_FILE} file at {path}")

    tree = None
    hashes = []
    for f, suffix in sources:
        data, sha = _read(f)
        hashes.append(sha)
        part = from_dict(data, sha256=sha, path=f, root_suffix=suffix)
        if tree is None:
            tree = part
            continue
        clash = set(tree.nodes) & set(part.nodes)
        if clash:
            raise ValueError(f"{f.name} and {tree.path.name} share ids ({sorted(clash)[:3]}…): read them separately")
        tree.nodes.update(part.nodes)
        tree.roots.update(part.roots)
        tree.sync_on = tree.sync_on or part.sync_on
        tree.files.append(str(f))
    tree.sha256 = hashlib.sha256("".join(hashes).encode()).hexdigest() if len(hashes) > 1 else hashes[0]
    tree.warnings = stale_warnings([f for f, _ in sources])
    return tree


def stale_warnings(files: list[Path]) -> list[str]:
    """Chrome also writes an encrypted copy of each file. If that copy is clearly newer,
    the plain file may have stopped being updated, and plans would be built on old data."""
    out = []
    for f in files:
        enc = f.with_name(("Encrypted" + f.name + "2"))
        try:
            gap = enc.stat().st_mtime - f.stat().st_mtime
        except OSError:
            continue
        if gap > 120:
            out.append(f"{f.name} is {int(gap)}s older than {enc.name}: the plain file may be stale; "
                       f"make one small bookmark change in the browser and check again")
    return out


def from_dict(data: dict, sha256: str = "", path: Path | None = None, root_suffix: str = "") -> Tree:
    nodes: dict[str, Node] = {}
    roots: dict[str, str] = {}
    prefix = "account:" if root_suffix else ""

    def walk(raw: dict, parent_id: str | None, index: int, trail: list[str], root: str) -> str:
        node = Node(
            id=str(raw["id"]),
            type=raw.get("type", "folder"),
            title=raw.get("name", ""),
            url=raw.get("url") if raw.get("type") == "url" else None,
            parent_id=parent_id,
            index=index,
            path=list(trail),
            root=root,
            date_added=raw.get("date_added"),
            date_last_used=raw.get("date_last_used"),
        )
        nodes[node.id] = node
        if node.is_folder:
            child_trail = trail + [node.title or ROOT_LABELS.get(root, "")]
            for i, child in enumerate(raw.get("children", [])):
                node.children.append(walk(child, node.id, i, child_trail, root))
        return node.id

    for key in ROOT_KEYS:
        raw_root = data.get("roots", {}).get(key)
        if raw_root is None:
            continue
        raw_root = dict(raw_root)
        label = ROOT_LABELS[key] + root_suffix
        raw_root["name"] = label  # browsers spell root names differently; use one label everywhere
        roots[prefix + key] = walk(raw_root, None, 0, [], prefix + key)

    return Tree(nodes, roots, sync_on="sync_metadata" in data, sha256=sha256, path=path)
