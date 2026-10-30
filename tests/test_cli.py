import json

from bookmarkwise.cli import main
from tests.helpers import DEMO, DRAFT


def test_full_cli_flow(tmp_path, capsys):
    inv = tmp_path / "inv.json"
    plan_path = tmp_path / "plan.json"
    assert main(["inventory", "--bookmarks", str(DEMO), "--out", str(inv)]) == 0
    assert json.loads(inv.read_text())["counts"]["bookmarks"] == 25
    assert main(["freeze", str(DRAFT), "--bookmarks", str(DEMO), "--out", str(plan_path)]) == 0
    assert main(["show", str(plan_path), "--limit", "3"]) == 0
    assert "| Now | Becomes |" in capsys.readouterr().out
    assert main(["build", str(plan_path), "--out", str(tmp_path / "ext")]) == 1
    assert main(["approve", str(plan_path)]) == 0
    assert main(["check", str(plan_path), "--bookmarks", str(DEMO)]) == 0
    assert main(["build", str(plan_path), "--out", str(tmp_path / "ext")]) == 0
    assert main(["verify", str(plan_path), "--bookmarks", str(DEMO)]) == 1  # nothing applied yet


def test_style_init_and_check(tmp_path, capsys):
    style = tmp_path / "style.json"
    assert main(["style", "init", "--style", str(style)]) == 0
    assert main(["style", "check", "--style", str(style)]) == 0
    assert main(["style", "init", "--style", str(style)]) == 1  # never overwrites the user's answers
