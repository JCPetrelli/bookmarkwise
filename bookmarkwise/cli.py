"""Command line: `python3 -m bookmarkwise <command>`. Every command only reads the Bookmarks file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import extension, inventory, linkcheck, model, profiles, style, undo
from . import plan as plan_mod


def _bookmarks_path(args) -> Path:
    if args.bookmarks:
        return Path(args.bookmarks).expanduser()
    if not args.profile:
        sys.exit("say which Bookmarks file: --bookmarks PATH, or --profile NAME (see `profiles`)")
    for p in profiles.find([args.browser]):
        if args.profile in (p["profile_dir"], p["profile_name"]):
            return Path(p["bookmarks_file"])
    sys.exit(f"no {args.browser} profile called {args.profile!r}: run `profiles` to list them")


def _source(p: argparse.ArgumentParser) -> None:
    p.add_argument("--bookmarks", help="path to a Bookmarks file")
    p.add_argument("--profile", help="profile folder or name, e.g. 'Default' or 'Profile 2'")
    p.add_argument("--browser", default="chrome", choices=sorted(profiles.BROWSERS))


def _write_json(data, path: str) -> None:
    Path(path).expanduser().write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def cmd_profiles(args) -> int:
    found = profiles.find([args.browser] if args.browser else None)
    if args.json:
        print(json.dumps(found, indent=2))
        return 0
    if not found:
        print("no profiles with a Bookmarks file found")
        return 1
    for p in found:
        sync = {True: "sync on", False: "sync off", None: "unreadable"}[p["sync_on"]]
        print(f"{p['browser_name']:<16} {p['profile_dir']:<12} {p['profile_name']:<24} {p['bookmarks'] or 0:>6} bookmarks  {sync}")
        print(f"{'':16} {p['bookmarks_file']}")
    return 0


def cmd_inventory(args) -> int:
    tree = model.load(_bookmarks_path(args))
    inv = inventory.build(tree)
    if args.out:
        _write_json(inv, args.out)
    print(inventory.summary(inv))
    if args.out:
        print(f"\nfull inventory: {args.out}")
    return 0


def cmd_style(args) -> int:
    if args.action == "init":
        try:
            print(f"wrote {style.init(args.style, force=args.force)}")
        except FileExistsError as e:
            print(e, file=sys.stderr)
            return 1
        return 0
    target = style.path(args.style)
    if not target.exists():
        print(f"no style file at {target}: run the interview, then `style init`")
        return 1
    data = style.load(args.style)
    if args.action == "show":
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    issues = style.problems(data)
    print("\n".join(issues) if issues else f"{target}: ok")
    return 1 if issues else 0


def cmd_freeze(args) -> int:
    draft = json.loads(Path(args.draft).read_text(encoding="utf-8"))
    tree = model.load(_bookmarks_path(args))
    try:
        frozen = plan_mod.freeze(draft, tree)
    except plan_mod.PlanError as e:
        print(e, file=sys.stderr)
        return 1
    plan_mod.save(frozen, args.out)
    counts = ", ".join(f"{n} {op}" for op, n in frozen["counts"].items())
    print(f"frozen {len(frozen['ops'])} operations ({counts}) -> {args.out}")
    print(f"plan {frozen['hash'][:8]}: show it with `show`, approve it only after the user says yes")
    return 0


def _row(op: dict) -> str:
    title = op.get("expect", {}).get("title") or op.get("title") or op.get("where", "")
    cells = {
        "delete": [title, op.get("expect", {}).get("url", "(folder)"), op.get("where", ""), op.get("reason", "")],
        "update": [title, " · ".join(f"{k}: {v}" for k, v in op.get("set", {}).items()), op.get("where", ""), op.get("reason", "")],
        "move": [title, op.get("where", ""), op.get("to", op.get("parent", "")), op.get("reason", "")],
        "create_folder": [op.get("title", ""), op.get("to", op.get("parent", "")), op.get("reason", "")],
        "create": [op.get("title", ""), op.get("url", ""), op.get("to", op.get("parent", "")), op.get("reason", "")],
        "sort": [title, "folders first" if op.get("folders_first") else "mixed", op.get("reason", "")],
        "order": [title, f"{len(op.get('children', []))} items", op.get("reason", "")],
    }[op["op"]]
    return "| " + " | ".join(str(c).replace("|", "\\|") for c in cells) + " |"


HEADERS = {
    "delete": "| Bookmark | URL | Folder | Why |",
    "update": "| Now | Becomes | Folder | Why |",
    "move": "| Bookmark | From | To | Why |",
    "create_folder": "| New folder | Inside | Why |",
    "create": "| New bookmark | URL | Folder | Why |",
    "sort": "| Folder | Order | Why |",
    "order": "| Folder | Items | Why |",
}


def cmd_show(args) -> int:
    p = plan_mod.load(args.plan)
    print(f"# {p['title']} (plan {p['hash'][:8]}, {p['status']})\n")
    for kind in plan_mod.OP_ORDER:
        ops = [o for o in p["ops"] if o["op"] == kind]
        if not ops:
            continue
        print(f"## {kind.replace('_', ' ')} ({len(ops)})\n")
        print(HEADERS[kind])
        print("|" + "---|" * HEADERS[kind].count(" | ") + "---|")
        for o in ops[: args.limit] if args.limit else ops:
            print(_row(o))
        if args.limit and len(ops) > args.limit:
            print(f"\n… and {len(ops) - args.limit} more")
        print()
    return 0


def cmd_approve(args) -> int:
    try:
        approved = plan_mod.approve(plan_mod.load(args.plan))
    except plan_mod.PlanError as e:
        print(e, file=sys.stderr)
        return 1
    plan_mod.save(approved, args.plan)
    print(f"plan {approved['hash'][:8]} approved ({len(approved['ops'])} operations)")
    return 0


def cmd_check(args) -> int:
    p = plan_mod.load(args.plan)
    drift = plan_mod.check(p, model.load(_bookmarks_path(args)))
    if not drift:
        print(f"no drift: all {len(p['ops'])} targets still match the plan")
        return 0
    print(f"{len(drift)} target(s) changed since the plan was frozen; rebuild the plan before applying:")
    for d in drift:
        print(f"  op {d['op']} {d['kind']}: {d['problem']}")
    return 1


def cmd_build(args) -> int:
    p = plan_mod.load(args.plan)
    try:
        out = extension.build(p, args.out, force=args.force)
    except plan_mod.PlanError as e:
        print(e, file=sys.stderr)
        return 1
    print(f"extension for plan {p['hash'][:8]} written to {out}")
    return 0


def cmd_verify(args) -> int:
    p = plan_mod.load(args.plan)
    rows = plan_mod.verify(p, model.load(_bookmarks_path(args)))
    bad = [r for r in rows if not r["ok"]]
    for r in rows if args.all else bad:
        print(f"  op {r['op']:>4} {r['kind']:<13} {'ok  ' if r['ok'] else 'MISSING'} {r['note']}")
    print(f"{len(rows) - len(bad)} of {len(rows)} operations are in the Bookmarks file")
    return 1 if bad else 0


def cmd_undo(args) -> int:
    p = plan_mod.load(args.plan)
    backup = json.loads(Path(args.backup).expanduser().read_text(encoding="utf-8"))
    draft = undo.build_draft(p, backup.get("tree", backup), model.load(_bookmarks_path(args)))
    _write_json(draft, args.out)
    print(f"undo draft with {len(draft['ops'])} operations -> {args.out}; freeze, show and approve it like any plan")
    return 0


def cmd_links(args) -> int:
    inv = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
    results = linkcheck.check(inv["bookmarks"], workers=args.workers, timeout=args.timeout)
    _write_json(results, args.out)
    gone = sum(1 for r in results if r["verdict"] == "gone")
    print(f"{gone} gone (404/410), {sum(1 for r in results if r['verdict'] == 'check')} to check, "
          f"{sum(1 for r in results if r['verdict'] == 'redirected')} redirected -> {args.out}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bookmarkwise", description="Plan, check and verify bookmark cleanups. Never writes the Bookmarks file.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("profiles", help="list browser profiles with a Bookmarks file")
    p.add_argument("--browser", choices=sorted(profiles.BROWSERS))
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_profiles)

    p = sub.add_parser("inventory", help="read-only inventory and findings")
    _source(p)
    p.add_argument("--out", help="write the full inventory JSON here")
    p.set_defaults(fn=cmd_inventory)

    p = sub.add_parser("style", help="the user's saved bookmark style")
    p.add_argument("action", choices=["init", "show", "check"])
    p.add_argument("--style", help=f"style file (default {style.DEFAULT_PATH})")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_style)

    p = sub.add_parser("freeze", help="snapshot and validate a draft plan")
    p.add_argument("draft")
    _source(p)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_freeze)

    p = sub.add_parser("show", help="print a plan as review tables")
    p.add_argument("plan")
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(fn=cmd_show)

    p = sub.add_parser("approve", help="mark a frozen plan approved (only after the user's yes)")
    p.add_argument("plan")
    p.set_defaults(fn=cmd_approve)

    p = sub.add_parser("check", help="is every target still as the plan expects?")
    p.add_argument("plan")
    _source(p)
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("build", help="write the one-off extension for an approved plan")
    p.add_argument("plan")
    p.add_argument("--out", required=True)
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_build)

    p = sub.add_parser("verify", help="after applying: is every change in the Bookmarks file?")
    p.add_argument("plan")
    _source(p)
    p.add_argument("--all", action="store_true", help="list every operation, not only missing ones")
    p.set_defaults(fn=cmd_verify)

    p = sub.add_parser("undo", help="draft an undo plan from the extension's backup")
    p.add_argument("plan")
    p.add_argument("--backup", required=True)
    _source(p)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_undo)

    p = sub.add_parser("links", help="optional: check which bookmarked pages still answer (uses the network)")
    p.add_argument("--inventory", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--timeout", type=float, default=10.0)
    p.set_defaults(fn=cmd_links)

    args = ap.parse_args(argv)
    return args.fn(args)
