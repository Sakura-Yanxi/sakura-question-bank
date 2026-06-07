from __future__ import annotations

import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "gaoshu_demo.sqlite3"
PORT = int(os.getenv("PORT", "8000"))


def check_http() -> dict:
    url = f"http://127.0.0.1:{PORT}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return {"ok": response.status == 200, "status": response.status, "url": url}
    except urllib.error.URLError as exc:
        return {"ok": False, "url": url, "error": str(exc)}


def check_db() -> dict:
    if not DB_PATH.exists():
        return {"ok": False, "path": str(DB_PATH), "error": "database file not found"}
    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'").fetchone()
        return {"ok": True, "path": str(DB_PATH), "tables": int(row[0] if row else 0)}
    except sqlite3.Error as exc:
        return {"ok": False, "path": str(DB_PATH), "error": str(exc)}


def dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def main() -> int:
    report = {
        "http": check_http(),
        "db": check_db(),
        "data_bytes": dir_size(DATA_DIR),
        "demo_mode": os.getenv("SAKURA_DEMO_MODE", "0") in {"1", "true", "True", "yes", "on"},
    }
    report["ok"] = bool(report["http"]["ok"] and report["db"]["ok"])
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
