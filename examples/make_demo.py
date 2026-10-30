"""Write the invented demo profile: examples/demo/Bookmarks.

Every title and URL here is made up for the demo (Acme Corp, the Harbor
project, example.org). Run: python3 examples/make_demo.py
"""

import json
from pathlib import Path

_next = [100]


def bm(title, url):
    _next[0] += 1
    return {"id": str(_next[0]), "type": "url", "name": title, "url": url, "date_added": "13370000000000000"}


def folder(title, *children):
    _next[0] += 1
    return {"id": str(_next[0]), "type": "folder", "name": title, "children": list(children), "date_added": "13370000000000000"}


bar = [
    bm("Inbox (12) - mail.example.org", "https://mail.example.org/inbox"),
    bm("ACME CORP - SPRINT BOARD - Agile Board - Jira", "https://acme-corp.atlassian.net/jira/software/projects/HAR/boards/7"),
    bm("Sprint board", "https://acme-corp.atlassian.net/jira/software/projects/HAR/boards/7?selectedIssue=HAR-311"),
    folder("Work",
        bm("Harbor API - Confluence", "https://acme-corp.atlassian.net/wiki/spaces/HAR/pages/1001/Harbor+API"),
        bm("Harbor API - Confluence", "https://acme-corp.atlassian.net/wiki/spaces/HAR/pages/1001/Harbor+API"),
        bm("Board", "https://acme-corp.atlassian.net/jira/software/projects/HAR/boards/7?quickFilter=12"),
        bm("Board", "https://acme-corp.atlassian.net/jira/software/projects/HAR/boards/7?quickFilter=19"),
        bm("localhost:3000", "http://localhost:3000/"),
        bm("Harbor staging", "https://staging.harbor.example.org/"),
        bm("192.168.1.40:8080/admin", "http://192.168.1.40:8080/admin"),
        bm("Sign in - Harbor Admin", "https://admin.harbor.example.org/login?next=%2Fdashboard"),
        bm("view-source:https://harbor.example.org/", "view-source:https://harbor.example.org/"),
        bm("Q3 roadmap - Google Sheets", "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit#gid=0"),
        folder("Old project (archived)",
            bm("legacy-harbor - GitHub", "https://github.com/acme-corp/legacy-harbor"),
        ),
        folder("Temp"),
    ),
    folder("Reading",
        bm("How to Write Clear Commit Messages | Example Blog", "https://blog.example.org/clear-commit-messages?utm_source=newsletter&utm_medium=email"),
        bm("How to Write Clear Commit Messages | Example Blog", "https://blog.example.org/clear-commit-messages"),
        bm("Python 3 documentation", "https://docs.python.org/3/"),
        bm("https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide", "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide"),
        bm("A very long article title that somebody pasted in full from the page header - Medium", "https://medium.example.org/p/long-article"),
    ),
    bm("Dark mode toggle", "javascript:(()=>{document.documentElement.classList.toggle('dark')})()"),
]

other = [
    bm("Recipes - example.org", "https://recipes.example.org/"),
    bm("Python 3 documentation", "https://docs.python.org/3/"),
    folder("Design",
        bm("Figma", "https://www.figma.com/files/recent"),
        bm("Harbor UI kit – Figma", "https://www.figma.com/design/AbC123/Harbor-UI-kit"),
        bm("Color contrast checker", "https://contrast.example.org/"),
    ),
]

data = {
    "checksum": "0" * 32,
    "roots": {
        "bookmark_bar": {"id": "1", "type": "folder", "name": "Bookmarks bar", "children": bar, "date_added": "13370000000000000"},
        "other": {"id": "2", "type": "folder", "name": "Other bookmarks", "children": other, "date_added": "13370000000000000"},
        "synced": {"id": "3", "type": "folder", "name": "Mobile bookmarks", "children": [], "date_added": "13370000000000000"},
    },
    "version": 1,
}

# Number nodes the way the browser does: a folder before its children.
counter = iter(range(4, 1000))


def renumber(node):
    node["id"] = str(next(counter))
    for child in node.get("children", []):
        renumber(child)


for top in bar + other:
    renumber(top)

out = Path(__file__).parent / "demo" / "Bookmarks"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(data, indent=3) + "\n")
print(f"wrote {out}")
