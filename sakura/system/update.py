from __future__ import annotations

import json
import re
import time
import urllib.request

# Latest-release lookup against the GitHub Releases API. The app only NOTIFIES about a newer
# version (and links to the download page); it never overwrites running code automatically.
GITHUB_API = "https://api.github.com/repos/{repo}/releases/latest"
GITHUB_RELEASES_PAGE = "https://github.com/{repo}/releases"
CACHE_TTL_SECONDS = 6 * 3600

# Module-level cache so we don't hit GitHub on every page load. Single value (one repo).
_CACHE: dict = {"checked_at": 0.0, "result": None}


def _parse_version(text: str) -> tuple:
    """'v1.2.3' / '1.2' -> a zero-padded 4-tuple of ints for ordering. Non-numeric -> (0,0,0,0)."""
    parts = [int(n) for n in re.findall(r"\d+", text or "")][:4]
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts)


def is_newer(latest: str, current: str) -> bool:
    return _parse_version(latest) > _parse_version(current)


def repo_configured(repo: str) -> bool:
    """Return True for a syntactically usable GitHub owner/repo slug.

    GitHub allows unusual repository names such as "-"; accept any non-empty
    owner/repo pair and let the API decide whether it exists.
    """
    repo = (repo or "").strip()
    if not repo or repo.endswith("/") or repo.count("/") != 1:
        return False
    owner, name = [part.strip() for part in repo.split("/", 1)]
    return bool(owner and name)


def releases_url(repo: str) -> str:
    return GITHUB_RELEASES_PAGE.format(repo=repo.strip()) if repo_configured(repo) else ""


def fetch_latest_release(repo: str, *, timeout: float = 4.0) -> dict | None:
    url = GITHUB_API.format(repo=repo)
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "Sakura-Update-Check"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    tag = str(data.get("tag_name") or "").strip()
    if not tag:
        return None
    return {
        "version": tag,
        "url": str(data.get("html_url") or f"https://github.com/{repo}/releases"),
        "notes": str(data.get("body") or "")[:2000],
        "published_at": str(data.get("published_at") or ""),
    }


def check_for_update(current_version: str, repo: str, *, now: float | None = None, force: bool = False) -> dict:
    """Return update info. NEVER raises: offline / rate-limited / private repo / unconfigured all
    degrade to 'no update available'. Result is cached for CACHE_TTL_SECONDS."""
    base = {
        "current": current_version,
        "latest": current_version,
        "update_available": False,
        "url": "",
        "notes": "",
        "checked": False,
        "configured": repo_configured(repo),
        "repo": repo.strip(),
        "releases_url": releases_url(repo),
    }
    if not base["configured"]:
        return base
    now = now if now is not None else time.time()
    cached = _CACHE.get("result")
    if not force and cached and (now - _CACHE.get("checked_at", 0.0)) < CACHE_TTL_SECONDS:
        return cached
    try:
        latest = fetch_latest_release(repo)
    except Exception:
        # Network error / GitHub rate limit / private repo — fall back to the last good result
        # if we have one, otherwise just report "no update". The banner simply won't show.
        return cached or base
    if not latest:
        result = base
    else:
        result = {
            "current": current_version,
            "latest": latest["version"],
            "update_available": is_newer(latest["version"], current_version),
            "url": latest["url"],
            "notes": latest["notes"],
            "published_at": latest.get("published_at", ""),
            "checked": True,
            "configured": True,
            "repo": repo.strip(),
            "releases_url": releases_url(repo),
        }
    _CACHE["result"] = result
    _CACHE["checked_at"] = now
    return result
