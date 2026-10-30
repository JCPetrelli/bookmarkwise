"""Build an undo draft from the backup the extension downloaded and the plan that ran.

The undo is itself a plan: freeze it against the current Bookmarks file, show
it, approve it, build a new extension. Re-created bookmarks get new ids (the
browser assigns them), and positions inside a folder can differ slightly.
"""

from __future__ import annotations

from .model import Tree


def index_backup(backup) -> dict[str, dict]:
    """Backup = the JSON of chrome.bookmarks.getTree(). Returns id -> node (with parentId)."""
    roots = backup if isinstance(backup, list) else backup.get("tree", backup)
    out: dict[str, dict] = {}
    stack = list(roots)
    while stack:
        n = stack.pop()
        out[str(n["id"])] = n
        stack.extend(n.get("children", []) or [])
    return out


def _recreate(node: dict, parent_ref: str, ops: list[dict], index: int | None) -> None:
    if "url" in node and node.get("url") is not None:
        op = {"op": "create", "parent": parent_ref, "title": node.get("title", ""), "url": node["url"],
              "key": f"restore-{node['id']}", "reason": f"restore deleted bookmark (was id {node['id']})"}
        if index is not None:
            op["index"] = index
        ops.append(op)
        return
    key = f"restore-{node['id']}"
    op = {"op": "create_folder", "key": key, "parent": parent_ref, "title": node.get("title", ""),
          "reason": f"restore deleted folder (was id {node['id']})"}
    if index is not None:
        op["index"] = index
    ops.append(op)
    for child in node.get("children", []) or []:
        _recreate(child, f"new:{key}", ops, None)  # children in original order, appended


def build_draft(plan: dict, backup, tree: Tree) -> dict:
    before = index_backup(backup)
    ops: list[dict] = []
    deleted = {o["id"] for o in plan["ops"] if o["op"] == "delete"}
    created_keys: dict[str, str | None] = {}

    def child_by_title(parent_id, title, url=None, folder=False):
        if parent_id is None or parent_id not in tree:
            return None
        for cid in tree[parent_id].children:
            c = tree[cid]
            if c.title == title and c.is_folder == folder and (url is None or c.url == url):
                return cid
        return None

    def parent_now(ref: str):
        return created_keys.get(ref[4:]) if ref.startswith("new:") else ref

    for o in plan["ops"]:
        kind = o["op"]
        if kind == "create_folder":
            created_keys[o["key"]] = child_by_title(parent_now(o["parent"]), o["title"], folder=True)

    for o in plan["ops"]:
        kind = o["op"]
        if kind == "delete":
            node = before.get(o["id"])
            if node is None:
                continue
            parent = str(node.get("parentId"))
            if parent in deleted:
                continue  # restored together with its folder
            _recreate(node, parent, ops, node.get("index"))
        elif kind == "update":
            back = {k: o["expect"][k] for k in o["set"] if k in o["expect"]}
            if o["id"] in tree:
                ops.append({"op": "update", "id": o["id"], **back, "reason": "restore previous title/URL"})
        elif kind == "move":
            if o["id"] in tree:
                op = {"op": "move", "id": o["id"], "parent": o["expect"]["parent"], "reason": "move back"}
                if o["id"] in before and before[o["id"]].get("index") is not None:
                    op["index"] = before[o["id"]]["index"]
                ops.append(op)
        elif kind == "create":
            cid = child_by_title(parent_now(o["parent"]), o["title"], o["url"])
            if cid:
                ops.append({"op": "delete", "id": cid, "reason": "remove bookmark the plan created"})

    for key, fid in created_keys.items():
        if fid:
            ops.append({"op": "delete", "id": fid, "reason": "remove folder the plan created"})

    # Put every folder the plan touched back in its original order. Re-created
    # items are referred to by their key, since their new ids are not known yet.
    affected: set[str] = set()
    for o in plan["ops"]:
        if o["op"] == "delete" and o["id"] in before:
            affected.add(str(before[o["id"]].get("parentId")))
        elif o["op"] == "move":
            affected.add(o["expect"]["parent"])
        elif o["op"] in ("sort", "order"):
            affected.add(o["id"])
        elif o["op"] in ("create", "create_folder") and not o["parent"].startswith("new:"):
            affected.add(o["parent"])
    for folder_id in sorted(affected):
        node = before.get(folder_id)
        if node is None or folder_id not in tree:
            continue
        refs = []
        for child in node.get("children", []) or []:
            cid = str(child["id"])
            if cid in deleted:
                refs.append(f"new:restore-{cid}")
            elif cid in tree:
                refs.append(cid)
        ops.append({"op": "order", "id": folder_id, "children": refs, "reason": "restore previous order"})

    return {"title": f"Undo: {plan.get('title', 'plan')}", "ops": ops}
