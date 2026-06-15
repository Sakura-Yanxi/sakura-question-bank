from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

# Latest-release lookup against the GitHub Releases API.
GITHUB_API = "https://api.github.com/repos/{repo}/releases/latest"
GITHUB_RELEASES_PAGE = "https://github.com/{repo}/releases"
CACHE_TTL_SECONDS = 6 * 3600
UPDATE_LOG_LIMIT = 6000
DEFAULT_UPDATE_BACKUP_KEEP = 3
MAX_UPDATE_BACKUP_KEEP = 20
UPDATE_BACKUP_KEEP_ENV = "SAKURA_UPDATE_BACKUP_KEEP"

CODE_DIRS = ("sakura", "static", "scripts", "tests", "docs", "deploy")
CODE_FILES = (
    ".env.example",
    ".gitattributes",
    ".gitignore",
    "app.py",
    "frontend-export.zip",
    "launch_server.vbs",
    "LICENSE",
    "notify_daily.py",
    "README.md",
    "requirements.txt",
    "run_server.bat",
    "update.bat",
    "update.sh",
)
REQUIRED_SOURCE_ENTRIES = ("app.py", "sakura", "static")
PRESERVED_CODE_PATHS = (Path("docs") / "software_copyright",)

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
        "zipball_url": str(data.get("zipball_url") or ""),
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
        "zipball_url": "",
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
            "zipball_url": latest.get("zipball_url", ""),
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


def _short_log(text: str, limit: int = UPDATE_LOG_LIMIT) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[-limit:]


def _run(args: list[str], root: Path, *, timeout: int = 300) -> dict:
    try:
        completed = subprocess.run(
            args,
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return {"ok": False, "code": 127, "output": f"未找到命令：{args[0]}"}
    except subprocess.TimeoutExpired as exc:
        return {"ok": False, "code": 124, "output": _short_log(exc.stdout or "命令执行超时。")}
    return {
        "ok": completed.returncode == 0,
        "code": completed.returncode,
        "output": _short_log(completed.stdout or ""),
    }


def _is_git_checkout(root: Path) -> bool:
    if not shutil.which("git"):
        return False
    result = _run(["git", "rev-parse", "--is-inside-work-tree"], root, timeout=10)
    return result["ok"] and "true" in result["output"].lower()


def update_capability(root: Path, info: dict | None = None) -> dict:
    root = Path(root)
    if _is_git_checkout(root):
        return {
            "supported": True,
            "mode": "git",
            "label": "一键更新",
            "description": "通过 git pull --ff-only 更新代码，并用当前 Python 环境安装依赖。",
        }
    if info and info.get("zipball_url"):
        return {
            "supported": True,
            "mode": "zip",
            "label": "一键更新",
            "description": "下载 GitHub Release 源码包覆盖代码；保留 data/、.env 和 .venv。",
        }
    return {
        "supported": False,
        "mode": "",
        "label": "下载新版",
        "description": "当前没有可自动更新的 Git 仓库或 Release zip，只能打开 Release 页面手动下载。",
    }


def disabled_capability(label: str, description: str, mode: str = "") -> dict:
    return {
        "supported": False,
        "mode": mode,
        "label": label,
        "description": description,
    }


def _backup_code(root: Path) -> str:
    backup_root = root / "data" / "update_backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    backup_path = backup_root / f"code-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for dirname in CODE_DIRS:
            source = root / dirname
            if source.exists():
                for path in source.rglob("*"):
                    if path.is_file():
                        archive.write(path, path.relative_to(root))
        for filename in CODE_FILES:
            source = root / filename
            if source.exists() and source.is_file():
                archive.write(source, source.relative_to(root))
    return str(backup_path.relative_to(root))


def _backup_keep_count() -> int:
    raw = os.getenv(UPDATE_BACKUP_KEEP_ENV, "").strip()
    if not raw:
        return DEFAULT_UPDATE_BACKUP_KEEP
    try:
        keep = int(raw)
    except ValueError:
        return DEFAULT_UPDATE_BACKUP_KEEP
    return max(1, min(keep, MAX_UPDATE_BACKUP_KEEP))


def _cleanup_empty_parents(path: Path, stop_at: Path) -> None:
    current = path
    stop_at = stop_at.resolve()
    try:
        current.resolve().relative_to(stop_at)
    except ValueError:
        return
    while current.exists():
        try:
            if current.resolve() == stop_at:
                break
            current.rmdir()
        except OSError:
            break
        current = current.parent


def _remove_backup_path(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_dir():
        size = sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
        shutil.rmtree(path)
        return size
    size = path.stat().st_size
    path.unlink()
    return size


def _cleanup_update_backups(root: Path, *, keep: int | None = None) -> dict:
    backup_root = root / "data" / "update_backups"
    if not backup_root.exists():
        return {"removed": 0, "freed_bytes": 0, "kept": keep or _backup_keep_count()}

    keep_count = keep if keep is not None else _backup_keep_count()
    removed = 0
    freed_bytes = 0
    for pattern in ("code-*.zip", "preserve-*"):
        candidates = [path for path in backup_root.glob(pattern) if path.exists()]
        candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        for path in candidates[keep_count:]:
            try:
                freed_bytes += _remove_backup_path(path)
                removed += 1
            except OSError:
                continue
    return {"removed": removed, "freed_bytes": freed_bytes, "kept": keep_count}


def _cleanup_step(root: Path) -> dict:
    cleanup = _cleanup_update_backups(root)
    freed_kb = cleanup["freed_bytes"] // 1024
    return {
        "name": "清理旧更新备份",
        "ok": True,
        "code": 0,
        "output": f"保留最近 {cleanup['kept']} 份，清理 {cleanup['removed']} 项，释放约 {freed_kb} KB。",
    }


def _safe_extract_zip(zip_path: Path, target: Path) -> Path:
    with zipfile.ZipFile(zip_path) as archive:
        names = [name for name in archive.namelist() if name and not name.endswith("/")]
        if not names:
            raise ValueError("Release zip 为空。")
        top_levels = {name.replace("\\", "/").split("/", 1)[0] for name in names}
        if len(top_levels) != 1:
            raise ValueError("Release zip 结构不符合 GitHub Source code 格式。")
        first = next(iter(top_levels))
        for name in names:
            normalized = name.replace("\\", "/")
            if normalized.startswith("/") or ".." in normalized.split("/"):
                raise ValueError("Release zip 中包含不安全路径。")
        archive.extractall(target)
    extracted_root = target / first
    if not extracted_root.exists() or not extracted_root.is_dir():
        raise ValueError("Release zip 结构不符合 GitHub Source code 格式。")
    return extracted_root


def _validate_source_root(source_root: Path) -> None:
    missing = [entry for entry in REQUIRED_SOURCE_ENTRIES if not (source_root / entry).exists()]
    if missing:
        raise ValueError(f"Release zip 缺少必要项目文件：{', '.join(missing)}")


def _move_preserved_code_paths(root: Path) -> list[tuple[Path, Path]]:
    stash_root = root / "data" / "update_backups" / f"preserve-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
    moved: list[tuple[Path, Path]] = []
    for relative in PRESERVED_CODE_PATHS:
        source = root / relative
        if not source.exists():
            continue
        target = stash_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        moved.append((relative, target))
    return moved


def _restore_preserved_code_paths(root: Path, moved: list[tuple[Path, Path]]) -> None:
    for relative, source in moved:
        destination = root / relative
        if destination.exists():
            if destination.is_dir():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        _cleanup_empty_parents(source.parent, root / "data" / "update_backups")


def _replace_code_from(source_root: Path, root: Path) -> None:
    _validate_source_root(source_root)
    moved = _move_preserved_code_paths(root)
    try:
        for dirname in CODE_DIRS:
            destination = root / dirname
            source = source_root / dirname
            if destination.exists():
                shutil.rmtree(destination)
            if source.exists():
                shutil.copytree(source, destination)
        for filename in CODE_FILES:
            destination = root / filename
            source = source_root / filename
            if destination.exists():
                destination.unlink()
            if source.exists() and source.is_file():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
    finally:
        _restore_preserved_code_paths(root, moved)


def _download_zip(url: str, destination: Path, *, timeout: int = 60) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "Sakura-Self-Update"})
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        with destination.open("wb") as out:
            shutil.copyfileobj(resp, out)


def _install_dependencies(root: Path) -> dict:
    requirements = root / "requirements.txt"
    if not requirements.exists():
        return {"ok": True, "code": 0, "output": "requirements.txt 不存在，跳过依赖安装。"}
    return _run(
        [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-r", str(requirements)],
        root,
        timeout=600,
    )


def apply_update(root: Path, current_version: str, repo: str) -> dict:
    root = Path(root)
    info = check_for_update(current_version, repo, force=True)
    if not info.get("configured"):
        return {"ok": False, "error": "未配置 GitHub 仓库，无法自动更新。", "info": info}
    if not info.get("checked"):
        return {"ok": False, "error": "暂时无法读取 GitHub Release，请稍后再试。", "info": info}
    if not info.get("update_available"):
        return {"ok": True, "message": "当前已经是最新版本。", "restart_required": False, "info": info}

    capability = update_capability(root, info)
    if not capability["supported"]:
        return {"ok": False, "error": capability["description"], "info": info, "auto_update": capability}

    steps: list[dict] = []
    backup = ""
    if capability["mode"] == "git":
        pull = _run(["git", "pull", "--ff-only"], root, timeout=180)
        steps.append({"name": "拉取代码", **pull})
        if not pull["ok"]:
            return {"ok": False, "error": "git pull 失败。", "steps": steps, "info": info, "auto_update": capability}
    else:
        try:
            backup = _backup_code(root)
            with TemporaryDirectory(prefix="sakura-update-") as tmp:
                tmp_path = Path(tmp)
                zip_path = tmp_path / "release.zip"
                _download_zip(str(info.get("zipball_url") or ""), zip_path)
                source_root = _safe_extract_zip(zip_path, tmp_path / "source")
                _replace_code_from(source_root, root)
            steps.append({"name": "下载并覆盖代码", "ok": True, "code": 0, "output": f"已备份旧代码到 {backup}"})
        except Exception as exc:
            steps.append({"name": "下载并覆盖代码", "ok": False, "code": 1, "output": str(exc)})
            return {"ok": False, "error": f"下载更新包失败：{exc}", "steps": steps, "info": info, "auto_update": capability}

    pip = _install_dependencies(root)
    steps.append({"name": "安装依赖", **pip})
    if not pip["ok"]:
        return {"ok": False, "error": "依赖安装失败。", "steps": steps, "info": info, "auto_update": capability}

    if backup:
        steps.append(_cleanup_step(root))

    return {
        "ok": True,
        "message": "更新已完成。请重启 Sakura 服务后生效。",
        "restart_required": True,
        "backup": backup,
        "steps": steps,
        "info": info,
        "auto_update": capability,
    }
