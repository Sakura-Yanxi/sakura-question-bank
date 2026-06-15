from __future__ import annotations

import threading
import traceback
from datetime import datetime
from pathlib import Path

from sakura.system import backup as sakura_backup


STALE_UPLOAD_SECONDS = 24 * 3600
_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()


def set_job(job_id: str, **updates) -> None:
    with _LOCK:
        job = _JOBS.setdefault(job_id, {})
        job.update(updates)
        job["updated_at"] = datetime.now().isoformat(timespec="seconds")


def get_job(job_id: str) -> dict | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        return dict(job) if job else None


def cleanup_stale_uploads(upload_dir: Path, *, max_age_seconds: int = STALE_UPLOAD_SECONDS) -> int:
    if not upload_dir.exists():
        return 0
    now = datetime.now().timestamp()
    removed = 0
    for path in upload_dir.glob("*.zip"):
        try:
            age = now - path.stat().st_mtime
            if age < max_age_seconds:
                continue
            path.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def run_import_job(
    job_id: str,
    upload_path: Path,
    *,
    root: Path,
    db_path: Path,
    folders: dict[str, Path],
    ensure_dirs,
    init_db,
) -> None:
    set_job(job_id, status="running", message="Restoring backup...")
    try:
        result = sakura_backup.restore_backup_zip(
            upload_path.read_bytes(),
            root=root,
            db_path=db_path,
            folders=folders,
            ensure_dirs=ensure_dirs,
            init_db=init_db,
        )
        set_job(job_id, status="done", message="Import completed.", result=result)
    except Exception as exc:
        traceback.print_exc()
        set_job(job_id, status="failed", message=str(exc), error=str(exc))
    finally:
        try:
            upload_path.unlink(missing_ok=True)
        except Exception:
            pass
