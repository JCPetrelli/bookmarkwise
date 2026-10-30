"""Plans: a draft written by Claude, frozen against the Bookmarks file, approved by the user.

Lifecycle:
  draft   -> `freeze` adds a snapshot of every target (title, URL, parent) and
             checks the plan can run (no roots touched, folders only deleted
             once empty, no two ops fighting over one bookmark).
  frozen  -> `approve` records the user's yes and the plan's hash.
  approved-> `build` refuses anything else, and refuses a plan edited after
             approval (its hash no longer matches).

Draft ops (ids are the ones in the Bookmarks file, which the extension API
uses too):
  {"op": "delete", "id": "42", "reason": "exact duplicate of 17"}
  {"op": "update", "id": "42", "title": "GitHub · dotfiles", "url": "https://..."}
  {"op": "move", "id": "42", "parent": "1" | "new:tools", "index": 0}
  {"op": "create_folder", "key": "tools", "parent": "1", "title": "Tools", "index": 0}
  {"op": "create", "parent": "1" | "new:tools", "title": "...", "url": "...", "index": 3, "key": "optional"}
  {"op": "sort", "id": "1", "folders_first": true}
  {"op": "order", "id": "1", "children": ["5", "new:restore-9", "7"]}   (used by undo plans)
Every op may carry a "reason" string, shown in the review tables.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .model import Tree

PLAN_FORMAT = 1
OP_ORDER = ["create_folder", "create", "update", "move", "delete", "sort", "order"]
ID_OPS = {"update", "move", "delete", "sort", "order"}


class PlanError(ValueError):
    """The plan cannot be frozen or built. The message says why."""


def ops_hash(ops: list[dict]) -> str:
    blob = json.dumps(ops, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _resolve_parent(ref: str, tree: Tree, keys: dict[str, str], errors: list[str], where: str) -> None:
    if isinstance(ref, str) and ref.startswith("new:"):
        if ref[4:] not in keys:
            errors.append(f"{where}: parent {ref!r} is not created by any create_folder op")
        return
    if ref not in tree:
        errors.append(f"{where}: parent {ref!r} is not in the Bookmarks file")
    elif not tree[ref].is_folder:
        errors.append(f"{where}: parent {ref!r} is a bookmark, not a folder")


def _parent_label(ref: str, tree: Tree, keys: dict[str, str]) -> str:
    if ref.startswith("new:"):
        return f"new folder {keys.get(ref[4:], ref[4:])!r}"
    if ref in tree:
        n = tree[ref]
        return " / ".join(n.path + [n.title])
    return ref


def freeze(draft: dict, tree: Tree) -> dict:
    ops_in = draft.get("ops")
    if not isinstance(ops_in, list) or not ops_in:
        raise PlanError("the draft has no ops")

    errors: list[str] = []
    keys: dict[str, str] = {}  # create_folder key -> title
    touched: dict[str, str] = {}  # id -> op that owns it (update/move/delete)
    frozen: list[dict] = []

    item_keys: set[str] = set()  # keys of created bookmarks, usable in "order" lists
    # First pass: collect folder keys so ops can point at folders created later in the list.
    for i, op in enumerate(ops_in):
        if op.get("op") == "create" and op.get("key"):
            if op["key"] in item_keys or op["key"] in keys:
                errors.append(f"op {i}: key {op['key']!r} is used twice")
            item_keys.add(op["key"])
        if op.get("op") == "create_folder":
            key = op.get("key")
            if not key or not isinstance(key, str):
                errors.append(f"op {i}: create_folder needs a 'key'")
            elif key in keys:
                errors.append(f"op {i}: folder key {key!r} is used twice")
            else:
                keys[key] = op.get("title", "")

    for i, op in enumerate(ops_in):
        kind = op.get("op")
        where = f"op {i} ({kind})"
        if kind not in OP_ORDER:
            errors.append(f"op {i}: unknown op {kind!r}")
            continue
        out = {"op": kind}
        if op.get("reason"):
            out["reason"] = str(op["reason"])

        if kind in ID_OPS:
            node_id = str(op.get("id", ""))
            if node_id not in tree:
                errors.append(f"{where}: id {node_id!r} is not in the Bookmarks file")
                continue
            node = tree[node_id]
            if node.is_root and kind not in ("sort", "order"):
                errors.append(f"{where}: {node.title!r} is a browser root folder and cannot be changed")
                continue
            if kind in ("update", "move", "delete"):
                if node_id in touched and not {touched[node_id], kind} == {"update", "move"}:
                    errors.append(f"{where}: id {node_id} is already in a {touched[node_id]} op")
                    continue
                touched.setdefault(node_id, kind)
            out["id"] = node_id
            out["expect"] = node.snapshot()
            out["expect"]["parent"] = node.parent_id
            out["where"] = node.location

        if kind == "update":
            changes = {k: op[k] for k in ("title", "url") if k in op}
            if not changes:
                errors.append(f"{where}: update needs a new 'title' or 'url'")
                continue
            if "url" in changes:
                if node.is_folder:
                    errors.append(f"{where}: a folder has no URL")
                    continue
                if not isinstance(changes["url"], str) or not changes["url"].strip():
                    errors.append(f"{where}: the new URL is empty")
                    continue
            if all(changes.get(k) == out["expect"].get(k) for k in changes):
                errors.append(f"{where}: nothing changes for id {node_id}")
                continue
            out["set"] = changes

        elif kind == "move":
            parent = str(op.get("parent", ""))
            _resolve_parent(parent, tree, keys, errors, where)
            if parent == node_id or (parent in tree and node_id in [a.id for a in _ancestors(tree, parent)]):
                errors.append(f"{where}: cannot move a folder into itself")
                continue
            out["parent"] = parent
            out["to"] = _parent_label(parent, tree, keys)
            if "index" in op:
                out["index"] = int(op["index"])

        elif kind == "create_folder":
            parent = str(op.get("parent", ""))
            _resolve_parent(parent, tree, keys, errors, where)
            out.update({"key": op.get("key"), "parent": parent, "title": op.get("title", "")})
            out["to"] = _parent_label(parent, tree, keys)
            if not out["title"]:
                errors.append(f"{where}: the new folder needs a title")
            if "index" in op:
                out["index"] = int(op["index"])

        elif kind == "create":
            parent = str(op.get("parent", ""))
            _resolve_parent(parent, tree, keys, errors, where)
            if not op.get("url"):
                errors.append(f"{where}: create needs a url (use create_folder for folders)")
            out.update({"parent": parent, "title": op.get("title", ""), "url": op.get("url", "")})
            if op.get("key"):
                out["key"] = op["key"]
            out["to"] = _parent_label(parent, tree, keys)
            if "index" in op:
                out["index"] = int(op["index"])

        elif kind == "sort":
            if not node.is_folder:
                errors.append(f"{where}: only folders can be sorted")
                continue
            out["folders_first"] = bool(op.get("folders_first", True))

        elif kind == "order":
            if not node.is_folder:
                errors.append(f"{where}: only folders can be ordered")
                continue
            out["children"] = [str(c) for c in op.get("children", [])]
            for c in out["children"]:
                if c.startswith("new:"):
                    if c[4:] not in keys and c[4:] not in item_keys:
                        errors.append(f"{where}: {c!r} is not created by this plan")
                elif c not in tree:
                    errors.append(f"{where}: child {c!r} is not in the Bookmarks file")

        frozen.append(out)

    if not errors:
        errors.extend(_check_deletes(frozen, tree))
    if errors:
        raise PlanError("the plan was not frozen:\n  " + "\n  ".join(errors))

    frozen.sort(key=lambda o: OP_ORDER.index(o["op"]))
    # Delete bookmarks before folders, deepest folders first, so each folder is empty when its turn comes.
    deletes = [o for o in frozen if o["op"] == "delete"]
    rest = [o for o in frozen if o["op"] != "delete"]
    deletes.sort(key=lambda o: (tree[o["id"]].is_folder, -len(tree[o["id"]].path)))
    ordered = [o for o in rest if OP_ORDER.index(o["op"]) < OP_ORDER.index("delete")] + deletes + \
              [o for o in rest if OP_ORDER.index(o["op"]) > OP_ORDER.index("delete")]

    plan = {
        "bookmarkwise_plan": PLAN_FORMAT,
        "title": draft.get("title", "Bookmark cleanup"),
        "created": _now(),
        "source": {
            "bookmarks_file": str(tree.path) if tree.path else None,
            "files": tree.files,
            "file_sha256": tree.sha256,
            "sync_on": tree.sync_on,
        },
        "status": "frozen",
        "counts": count_ops(ordered),
        "ops": ordered,
    }
    plan["hash"] = ops_hash(ordered)
    return plan


def _ancestors(tree: Tree, node_id: str):
    node = tree[node_id]
    while node.parent_id is not None:
        node = tree[node.parent_id]
        yield node


def _check_deletes(ops: list[dict], tree: Tree) -> list[str]:
    """A folder may be deleted only if it ends up empty: everything in it deleted or moved out."""
    deleted = {o["id"] for o in ops if o["op"] == "delete"}
    moved_to = {o["id"]: o["parent"] for o in ops if o["op"] == "move"}
    errors = []
    for o in ops:
        if o["op"] != "delete" or not tree[o["id"]].is_folder:
            continue
        folder = o["id"]
        left = [c for c in tree[folder].children if c not in deleted and c not in moved_to]
        moved_in = [nid for nid, parent in moved_to.items() if parent == folder]
        if left or moved_in:
            names = ", ".join(repr(tree[c].title) for c in (left + moved_in)[:3])
            errors.append(
                f"delete folder {tree[folder].title!r} (id {folder}): it would still hold "
                f"{len(left) + len(moved_in)} item(s), e.g. {names}. Delete or move them in the same plan."
            )
        # A move into a folder that is being deleted is caught above; a move into a deleted
        # folder's subfolder is caught when that subfolder's own delete is checked.
    for nid, parent in moved_to.items():
        if parent in deleted:
            errors.append(f"move id {nid}: its target folder (id {parent}) is deleted by the same plan")
    return errors


def count_ops(ops: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for o in ops:
        counts[o["op"]] = counts.get(o["op"], 0) + 1
    return counts


def approve(plan: dict) -> dict:
    if plan.get("bookmarkwise_plan") != PLAN_FORMAT:
        raise PlanError("this is not a frozen Bookmarkwise plan: run `freeze` first")
    if plan.get("hash") != ops_hash(plan["ops"]):
        raise PlanError("the plan's ops changed after freezing: freeze it again")
    plan = dict(plan)
    plan["status"] = "approved"
    plan["approved"] = _now()
    return plan


def assert_buildable(plan: dict) -> None:
    if plan.get("bookmarkwise_plan") != PLAN_FORMAT:
        raise PlanError("this is not a frozen Bookmarkwise plan")
    if plan.get("status") != "approved":
        raise PlanError("the plan is not approved: show it to the user, then run `approve` after their yes")
    if plan.get("hash") != ops_hash(plan["ops"]):
        raise PlanError("the plan was edited after approval: freeze and approve it again")


def check(plan: dict, tree: Tree) -> list[dict]:
    """Ops whose target no longer matches its snapshot. Empty list = safe to apply."""
    drift = []
    for i, o in enumerate(plan["ops"]):
        if "id" not in o:
            parent = o.get("parent", "")
            if not parent.startswith("new:") and parent not in tree:
                drift.append({"op": i, "kind": o["op"], "problem": f"parent folder {parent} is gone"})
            continue
        if o["id"] not in tree:
            drift.append({"op": i, "kind": o["op"], "id": o["id"], "problem": "bookmark is gone"})
            continue
        node = tree[o["id"]]
        exp = o["expect"]
        for field in ("title", "url"):
            if field in exp and (node.title if field == "title" else node.url) != exp[field]:
                now = node.title if field == "title" else node.url
                drift.append({"op": i, "kind": o["op"], "id": o["id"],
                              "problem": f"{field} changed: {exp[field]!r} -> {now!r}"})
        if exp.get("parent") != node.parent_id:
            drift.append({"op": i, "kind": o["op"], "id": o["id"], "problem": "moved to another folder"})
    return drift


def verify(plan: dict, tree: Tree) -> list[dict]:
    """After the extension ran: one row per op, `ok` true when the file shows the change."""
    rows = []
    created: dict[str, str | None] = {}

    def find_child(parent_id: str | None, title: str, url: str | None = None, folder: bool = False):
        if parent_id is None or parent_id not in tree:
            return None
        for cid in tree[parent_id].children:
            c = tree[cid]
            if c.title == title and c.is_folder == folder and (url is None or c.url == url):
                return cid
        return None

    def parent_id_of(ref: str):
        return created.get(ref[4:]) if ref.startswith("new:") else ref

    for i, o in enumerate(plan["ops"]):
        kind = o["op"]
        ok, note = False, ""
        if kind == "create_folder":
            fid = find_child(parent_id_of(o["parent"]), o["title"], folder=True)
            created[o["key"]] = fid
            ok, note = fid is not None, f"folder {o['title']!r}"
        elif kind == "create":
            ok = find_child(parent_id_of(o["parent"]), o["title"], o["url"]) is not None
            note = f"{o['title']!r}"
        elif kind == "delete":
            ok, note = o["id"] not in tree, f"{o['expect'].get('title')!r} removed"
        elif o["id"] not in tree:
            ok, note = False, "bookmark is gone"
        elif kind == "update":
            node = tree[o["id"]]
            ok = all((node.title if k == "title" else node.url) == v for k, v in o["set"].items())
            note = f"now {node.title!r}"
        elif kind == "move":
            node = tree[o["id"]]
            target = parent_id_of(o["parent"])
            ok, note = node.parent_id == target and target is not None, f"in {node.location!r}"
        elif kind == "sort":
            kids = [tree[c] for c in tree[o["id"]].children]
            ok = [k.id for k in kids] == [k.id for k in sorted(kids, key=lambda k: sort_key(k, o["folders_first"]))]
            note = f"{len(kids)} items"
        elif kind == "order":
            present = [c for c in o["children"] if c in tree and tree[c].parent_id == o["id"]]
            actual = [c for c in tree[o["id"]].children if c in present]
            ok, note = actual == present, f"{len(present)} items"
        rows.append({"op": i, "kind": kind, "id": o.get("id"), "ok": ok, "note": note})
    return rows


def sort_key(node, folders_first: bool):
    """Same rule as the extension: optional folders first, then lower-cased title, then the raw title."""
    return (0 if (folders_first and node.is_folder) else 1, node.title.lower(), node.title)


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(plan: dict, path: str | Path) -> None:
    Path(path).write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
