"""Optional dead-link check. Off by default: it contacts every bookmarked site.

Only http(s) URLs that are not local are checked. Each site sees one HEAD
request (GET if HEAD is refused), the same as opening the bookmark would.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .inventory import is_local

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


def probe(url: str, timeout: float = 10.0) -> dict:
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return {"url": url, "status": resp.status, "final_url": resp.geturl()}
        except urllib.error.HTTPError as e:
            if method == "HEAD" and e.code in (403, 405, 501):
                continue
            return {"url": url, "status": e.code}
        except Exception as e:  # DNS, TLS, timeout: reported, never fatal
            return {"url": url, "status": None, "error": type(e).__name__}
    return {"url": url, "status": None, "error": "no answer"}


def check(bookmarks: list[dict], workers: int = 8, timeout: float = 10.0) -> list[dict]:
    targets = [b for b in bookmarks if b.get("url", "").startswith(("http://", "https://")) and not is_local(b["url"])]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda b: probe(b["url"], timeout), targets))
    out = []
    for b, r in zip(targets, results):
        status = r.get("status")
        verdict = "ok" if status and status < 400 else "gone" if status in (404, 410) else "check"
        if verdict != "ok" or (r.get("final_url") and r["final_url"].rstrip("/") != b["url"].rstrip("/")):
            out.append({**b, **r, "verdict": verdict if verdict != "ok" else "redirected"})
    return out
