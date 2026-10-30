from bookmarkwise import inventory, model
from tests.helpers import DEMO


def test_normalize_drops_decoration_only():
    a = inventory.normalize_url("https://www.example.org/page/?utm_source=x&b=2&a=1#top")
    b = inventory.normalize_url("http://example.org/page?a=1&b=2")
    assert a == b
    assert inventory.normalize_url("https://example.org/p?id=1") != inventory.normalize_url("https://example.org/p?id=2")


def test_pinned_state_counts_as_same_page():
    board = "https://acme-corp.atlassian.net/jira/boards/7"
    assert inventory.normalize_url(board + "?selectedIssue=HAR-1") == inventory.normalize_url(board)


def test_url_kinds():
    k = inventory.url_kind
    assert k("javascript:alert(1)") == "bookmarklet"
    assert k("view-source:https://example.org") == "view-source"
    assert k("chrome://settings") == "browser-internal"
    assert k("http://localhost:3000/") == "local"
    assert k("http://192.168.1.40:8080/") == "local"
    assert k("http://printer.local/") == "local"
    assert k("https://example.org/login?next=/home") == "login-redirect"
    assert k("https://www.google.com/url?q=https://example.org") == "redirect"
    assert k("https://cms.example.org/posts/4/edit") == "edit-or-draft"
    assert k("https://docs.google.com/spreadsheets/d/abc/edit") is None
    assert k("https://example.org/a?utm_medium=email") == "tracking-params"
    assert k("https://example.org/about") is None


def test_title_issues():
    assert "site-suffix" in inventory.title_issues("How to Write Clear Commit Messages | Example Blog", None)
    assert "all-caps" in inventory.title_issues("ACME SPRINT BOARD", None)
    assert inventory.title_issues("https://x.org", "https://x.org") == ["title-is-url"]
    assert inventory.title_issues("", "https://x.org") == ["no-title"]
    assert inventory.title_issues("Docs · Python 3", None) == []


def test_strip_tracking_keeps_the_rest():
    assert inventory.strip_tracking("https://e.org/a?x=1&utm_source=n#f") == "https://e.org/a?x=1#f"


def test_demo_inventory_counts():
    inv = inventory.build(model.load(DEMO))
    c = inv["counts"]
    assert c["bookmarks"] == 25
    assert c["exact_duplicate_groups"] == 2
    assert c["near_duplicate_groups"] == 2
    assert c["empty_folders"] == 1
    assert "bookmarks" in inventory.summary(inv)
