import json

import pytest

from bookmarkwise import extension, model, plan, undo
from tests.helpers import DEMO, DRAFT, backup_from, demo_dict, shape, simulate, write


def frozen(tree=None):
    return plan.freeze(json.loads(DRAFT.read_text()), tree or model.load(DEMO))


def test_freeze_orders_and_snapshots():
    p = frozen()
    kinds = [o["op"] for o in p["ops"]]
    assert kinds == sorted(kinds, key=plan.OP_ORDER.index)
    assert p["counts"] == {"create_folder": 1, "update": 15, "move": 2, "delete": 9, "sort": 1}
    deletes = [o for o in p["ops"] if o["op"] == "delete"]
    assert deletes[-1]["expect"]["title"] in ("Old project (archived)", "Temp")  # folders last
    upd = next(o for o in p["ops"] if o["op"] == "update")
    assert upd["expect"]["title"] and upd["expect"]["parent"]


@pytest.mark.parametrize("ops, message", [
    ([{"op": "delete", "id": "1"}], "root folder"),
    ([{"op": "delete", "id": "999"}], "not in the Bookmarks file"),
    ([{"op": "delete", "id": "7"}], "would still hold"),
    ([{"op": "update", "id": "4"}], "needs a new"),
    ([{"op": "update", "id": "4", "title": "Inbox (12) - mail.example.org"}], "nothing changes"),
    ([{"op": "update", "id": "7", "url": "https://x"}], "folder has no URL"),
    ([{"op": "delete", "id": "4"}, {"op": "update", "id": "4", "title": "x"}], "already in a delete"),
    ([{"op": "move", "id": "7", "parent": "21"}, {"op": "delete", "id": "21"}], "deleted by the same plan"),
    ([{"op": "move", "id": "4", "parent": "new:nope"}], "not created by any"),
    ([{"op": "move", "id": "7", "parent": "18"}], "into itself"),
    ([{"op": "move", "id": "4", "parent": "5"}], "not a folder"),
    ([{"op": "explode", "id": "4"}], "unknown op"),
])
def test_freeze_refuses(ops, message):
    with pytest.raises(plan.PlanError, match=message):
        plan.freeze({"ops": ops}, model.load(DEMO))


def test_update_then_move_same_bookmark_is_allowed():
    p = plan.freeze({"ops": [{"op": "update", "id": "4", "title": "Mail · Inbox"},
                             {"op": "move", "id": "4", "parent": "21"}]}, model.load(DEMO))
    data, statuses = simulate(demo_dict(), p)
    assert statuses == ["done", "done"]


def test_approve_and_tamper():
    p = frozen()
    with pytest.raises(plan.PlanError, match="not approved"):
        plan.assert_buildable(p)
    a = plan.approve(p)
    plan.assert_buildable(a)
    a["ops"][0]["title"] = "sneaky"
    with pytest.raises(plan.PlanError, match="edited after approval"):
        plan.assert_buildable(a)


def test_check_finds_drift(tmp_path):
    p = frozen()
    assert plan.check(p, model.load(DEMO)) == []
    data = demo_dict()
    data["roots"]["bookmark_bar"]["children"][0]["name"] = "Renamed by hand"
    drift = plan.check(p, model.load(write(tmp_path, data)))
    assert len(drift) == 1 and "title changed" in drift[0]["problem"]


def test_simulated_apply_then_verify_then_undo(tmp_path):
    original = demo_dict()
    p = plan.approve(frozen())
    after, statuses = simulate(original, p)
    assert statuses == ["done"] * len(p["ops"])
    after_tree = model.load(write(tmp_path, after))
    assert all(r["ok"] for r in plan.verify(p, after_tree))
    assert not all(r["ok"] for r in plan.verify(p, model.load(DEMO)))

    draft = undo.build_draft(p, backup_from(original)["tree"], after_tree)
    undo_plan = plan.approve(plan.freeze(draft, after_tree))
    restored, statuses = simulate(after, undo_plan)
    assert "skipped" not in statuses
    assert shape(restored) == shape(original)


def test_extension_build(tmp_path):
    p = frozen()
    with pytest.raises(plan.PlanError):
        extension.build(p, tmp_path / "ext")
    out = extension.build(plan.approve(p), tmp_path / "ext")
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["permissions"] == ["bookmarks"]
    assert p["hash"][:8] in manifest["name"]
    js = (out / "plan.js").read_text()
    assert js.startswith("// Generated") and "const PLAN = " in js
    with pytest.raises(plan.PlanError, match="already exists"):
        extension.build(plan.approve(p), out)
    other = tmp_path / "not-ours"
    other.mkdir()
    with pytest.raises(plan.PlanError, match="not a Bookmarkwise"):
        extension.build(plan.approve(p), other, force=True)


def test_extension_js_parses(tmp_path):
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    out = extension.build(plan.approve(frozen()), tmp_path / "ext")
    for f in ("apply.js", "plan.js", "background.js"):
        subprocess.run([node, "--check", str(out / f)], check=True)
