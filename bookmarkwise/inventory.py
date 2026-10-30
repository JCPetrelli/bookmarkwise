"""Read-only inventory: every bookmark plus the findings a cleanup plan starts from.

Findings are suggestions, not decisions. Which of them become deletions or
renames depends on the user's style file and on their approval.
"""

from __future__ import annotations

import ipaddress
from pathlib import Path
import re
from collections import Counter, defaultdict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .model import Tree

TRACKING_PARAMS = {
    "fbclid", "gclid", "dclid", "gbraid", "wbraid", "msclkid", "mc_cid", "mc_eid", "igshid",
    "yclid", "_hsenc", "_hsmi", "mkt_tok", "ref_src", "si", "spm", "trk", "trkCampaign",
}
TRACKING_PREFIXES = ("utm_", "pk_", "vero_", "oly_")
# Page state that pins one view of the same page (an open ticket, a focused comment).
STATE_PARAMS = {"selectedIssue", "focusedCommentId", "focusedId", "preview", "modal"}
# Sites where /edit is the normal address of the document, not a draft screen.
EDIT_IS_NORMAL = ("docs.google.com",)

REDIRECT_HOSTS = {"l.facebook.com", "lm.facebook.com", "l.instagram.com", "out.reddit.com", "t.co", "lnkd.in"}
LOGIN_PATH = re.compile(r"/(log-?in|sign-?in|signin|auth|oauth2?|sso|saml|cas/login)(/|$|\?)", re.I)
RETURN_PARAMS = {"next", "continue", "returnurl", "return_to", "redirect", "redirect_uri", "redirect_url", "service"}
EDIT_PATH = re.compile(r"/(edit|draft|drafts|compose|new)(/|$)", re.I)
SITE_SUFFIX = re.compile(r"\s+[-–—|·•:]\s+[^-–—|·•:]{2,40}$")


def normalize_url(url: str) -> str:
    """The key used for near-duplicates: same page, different decoration.

    Drops the fragment, tracking and page-state parameters, `www.`, the scheme difference
    between http and https, default ports and a trailing slash, and sorts the
    remaining query parameters.
    """
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url
    if parts.scheme not in ("http", "https"):
        return url.strip()
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    port = parts.port
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    query = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k not in TRACKING_PARAMS and k not in STATE_PARAMS and not k.lower().startswith(TRACKING_PREFIXES)
    ]
    path = parts.path.rstrip("/") or ""
    return urlunsplit(("http", netloc, path, urlencode(sorted(query)), ""))


def strip_tracking(url: str) -> str:
    """Remove tracking parameters only; keep everything else as it was."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if parts.scheme not in ("http", "https") or not parts.query:
        return url
    kept = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k not in TRACKING_PARAMS and not k.lower().startswith(TRACKING_PREFIXES)
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment))


def is_local(url: str) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if parts.scheme == "file":
        return True
    host = (parts.hostname or "").lower()
    if not host:
        return False
    if host in ("localhost", "0.0.0.0") or host.endswith((".local", ".localhost", ".lan", ".internal", ".home.arpa")):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


def url_kind(url: str) -> str | None:
    """A short label for URLs that are rarely worth keeping as they are."""
    lower = url.lower()
    if lower.startswith("javascript:"):
        return "bookmarklet"  # a tool, not a page: keep unless the user says otherwise
    if lower.startswith("view-source:"):
        return "view-source"
    if lower.startswith(("chrome://", "edge://", "brave://", "about:", "chrome-extension://", "data:")):
        return "browser-internal"
    if is_local(url):
        return "local"
    try:
        parts = urlsplit(url)
    except ValueError:
        return "malformed"
    if parts.scheme not in ("http", "https"):
        return "other-scheme"
    host = (parts.hostname or "").lower()
    params = {k.lower() for k, _ in parse_qsl(parts.query, keep_blank_values=True)}
    if host in REDIRECT_HOSTS or (host.endswith("google.com") and parts.path == "/url"):
        return "redirect"
    if LOGIN_PATH.search(parts.path) or params & RETURN_PARAMS:
        return "login-redirect"
    if EDIT_PATH.search(parts.path) and not host.endswith(EDIT_IS_NORMAL):
        return "edit-or-draft"
    if params & {p.lower() for p in STATE_PARAMS}:
        return "pinned-state"
    if url != strip_tracking(url):
        return "tracking-params"
    return None


def title_issues(title: str, url: str | None) -> list[str]:
    issues = []
    t = title.strip()
    if not t:
        issues.append("no-title")
        return issues
    if url and t == url:
        issues.append("title-is-url")
    if len(t) > 60:
        issues.append("long")
    letters = [c for c in t if c.isalpha()]
    if len(letters) >= 6 and all(c.isupper() for c in letters):
        issues.append("all-caps")
    if SITE_SUFFIX.search(t) and len(t) > 25:
        issues.append("site-suffix")
    if t != title:
        issues.append("spaces")
    return issues


def domain(url: str) -> str:
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def build(tree: Tree) -> dict:
    marks = tree.bookmarks()
    by_url: dict[str, list] = defaultdict(list)
    by_norm: dict[str, list] = defaultdict(list)
    for n in marks:
        by_url[n.url].append(n)
        by_norm[normalize_url(n.url)].append(n)

    exact = [[m.to_dict() for m in group] for group in by_url.values() if len(group) > 1]
    exact_urls = {url for url, group in by_url.items() if len(group) > 1}
    near = []
    for group in by_norm.values():
        urls = {m.url for m in group}
        if len(urls) > 1:  # differs only by decoration; exact copies are reported above
            near.append([m.to_dict() for m in group])

    flagged = []
    for n in marks:
        kind = url_kind(n.url)
        issues = title_issues(n.title, n.url)
        if kind or issues:
            item = n.to_dict()
            if kind:
                item["kind"] = kind
            if issues:
                item["title_issues"] = issues
            if n.url in exact_urls:
                item["exact_duplicate"] = True
            flagged.append(item)

    empty = [f.to_dict() for f in tree.folders() if not f.children]
    folders = []
    for f in tree.folders(include_roots=True):
        direct = sum(1 for c in f.children if tree[c].type == "url")
        sub = sum(1 for c in f.children if tree[c].is_folder)
        folders.append({"id": f.id, "path": " / ".join(f.path + [f.title]), "bookmarks": direct, "folders": sub, "root": f.is_root})

    domains = Counter(domain(n.url) for n in marks if n.url.startswith(("http://", "https://")))

    return {
        "bookmarks_file": str(tree.path) if tree.path else None,
        "files": tree.files,
        "warnings": tree.warnings,
        "file_sha256": tree.sha256,
        "sync_on": tree.sync_on,
        "counts": {
            "bookmarks": len(marks),
            "folders": len(tree.folders()),
            "exact_duplicate_groups": len(exact),
            "near_duplicate_groups": len(near),
            "flagged": len(flagged),
            "empty_folders": len(empty),
        },
        "folders": folders,
        "top_domains": domains.most_common(25),
        "exact_duplicates": exact,
        "near_duplicates": near,
        "flagged": flagged,
        "empty_folders": empty,
        "bookmarks": [n.to_dict() for n in marks],
    }


def summary(inv: dict) -> str:
    c = inv["counts"]
    lines = [
        f"bookmarks                {c['bookmarks']}",
        f"folders                  {c['folders']}",
        f"exact duplicate groups   {c['exact_duplicate_groups']}",
        f"near duplicate groups    {c['near_duplicate_groups']}",
        f"flagged bookmarks        {c['flagged']}",
        f"empty folders            {c['empty_folders']}",
        f"sync                     {'on' if inv['sync_on'] else 'off or unknown'}",
    ]
    for w in inv.get("warnings", []):
        lines.insert(0, f"WARNING: {w}")
    if len(inv.get("files", [])) > 1:
        lines.append("files                    " + ", ".join(Path(f).name for f in inv["files"]))
    kinds = Counter(f.get("kind") for f in inv["flagged"] if f.get("kind"))
    if kinds:
        lines.append("")
        lines.append("flagged by kind:")
        for kind, n in kinds.most_common():
            lines.append(f"  {kind:<22} {n}")
    issues = Counter(i for f in inv["flagged"] for i in f.get("title_issues", []))
    if issues:
        lines.append("title issues:")
        for issue, n in issues.most_common():
            lines.append(f"  {issue:<22} {n}")
    return "\n".join(lines)
