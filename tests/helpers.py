"""Test helpers: the demo file, and a small Python stand-in for the extension.

`simulate` applies a frozen plan to a Bookmarks dict with the same rules as
apply.js (snapshot check per op, empty-folder-only deletes, sort rule), so
plan/verify/undo can be tested without a browser. tests/e2e runs the real one.
"""

import copy
import json
from pathlib import Path

DEMO = Path(__file__).resolve().parent.parent / "examples" / "demo" / "Bookmarks"
DRAFT = Path(__file__).resolve().parent.parent / "examples" / "demo-draft.json"


def demo_dict():
    return json.loads(DEMO.read_text())


def write(tmp_path, data, name="Bookmarks"):
    p = tmp_path / name
    p.write_text(json.dumps(data))
    return p


def _index(data):
    nodes, parents = {}, {}

    def walk(n, parent):
        nodes[n["id"]] = n
        parents[n["id"]] = parent
        for c in n.get("children", []):
            walk(c, n["id"])

    for r in data["roots"].values():
        walk(r, None)
    return nodes, parents


def simulate(data, plan):
    """Apply a frozen plan to a copy of `data`. Returns (new_data, statuses)."""
    data = copy.deepcopy(data)
    nodes, parents = _index(data)
    next_id = [max(int(i) for i in nodes) + 1]
    keys, statuses = {}, []

    def ref(r):
        return keys.get(r[4:]) if r.startswith("new:") else r

    def detach(nid):
        p = nodes[parents[nid]]
        p["children"] = [c for c in p["children"] if c["id"] != nid]

    def insert(node, parent_id, index):
        kids = nodes[parent_id].setdefault("children", [])
        index = len(kids) if index is None else max(0, min(index, len(kids)))
        kids.insert(index, node)
        nodes[node["id"]] = node
        parents[node["id"]] = parent_id

    expected = {}
    for op in plan["ops"]:
        kind = op["op"]
        if kind in ("create", "create_folder"):
            pid = ref(op["parent"])
            new = {"id": str(next_id[0]), "name": op["title"], "type": "url" if kind == "create" else "folder"}
            next_id[0] += 1
            if kind == "create":
                new["url"] = op["url"]
            else:
                new["children"] = []
            insert(new, pid, op.get("index"))
            if op.get("key"):
                keys[op["key"]] = new["id"]
            statuses.append("done")
            continue
        exp = expected.setdefault(op["id"], dict(op["expect"]))
        n = nodes.get(op["id"])
        if (n is None or ("title" in exp and n["name"] != exp["title"]) or ("url" in exp and n.get("url") != exp["url"])
                or (exp.get("parent") is not None and parents.get(op["id"]) != exp["parent"])):
            statuses.append("skipped")
            continue
        if kind == "update":
            if "title" in op["set"]:
                n["name"] = op["set"]["title"]
                exp["title"] = n["name"]
            if "url" in op["set"]:
                n["url"] = op["set"]["url"]
                exp["url"] = n["url"]
        elif kind == "move":
            pid = ref(op["parent"])
            detach(op["id"])
            insert(n, pid, op.get("index"))
            exp["parent"] = pid
        elif kind == "delete":
            if n.get("type") == "folder" and n.get("children"):
                statuses.append("skipped")
                continue
            detach(op["id"])
            del nodes[op["id"]]
        elif kind == "sort":
            ff = op["folders_first"]
            n["children"].sort(key=lambda c: (0 if ff and c.get("type") == "folder" else 1, c["name"].lower(), c["name"]))
        elif kind == "order":
            wanted = [ref(r) for r in op["children"]]
            here = [c for c in n["children"]]
            by_id = {c["id"]: c for c in here}
            first = [by_id[i] for i in wanted if i in by_id]
            n["children"] = first + [c for c in here if c["id"] not in wanted]
        statuses.append("done")
    return data, statuses


def shape(data):
    def walk(n):
        return [n["name"], n["url"]] if n.get("type") == "url" else [n["name"], [walk(c) for c in n.get("children", [])]]
    return [[walk(c) for c in data["roots"][k].get("children", [])] for k in ("bookmark_bar", "other", "synced")]


def backup_from(data):
    """What chrome.bookmarks.getTree() returns for this data (the extension's backup)."""
    def walk(n, parent, index):
        out = {"id": n["id"], "title": n["name"], "parentId": parent, "index": index}
        if n.get("type") == "url":
            out["url"] = n["url"]
        else:
            out["children"] = [walk(c, n["id"], i) for i, c in enumerate(n.get("children", []))]
        return out
    roots = [walk(data["roots"][k], "0", i) for i, k in enumerate(("bookmark_bar", "other", "synced"))]
    return {"tree": [{"id": "0", "title": "", "children": roots}]}
