from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path


def build_backup_zip_file(target: Path, db_path: Path, folders: dict[str, Path]) -> Path:
    """Build a Sakura migration archive containing database and generated assets."""
    manifest = {
        "app": "Sakura做题集",
        "version": 1,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "includes": ["database", "uploads", "pages", "textbooks"],
    }
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        if db_path.exists():
            zf.write(db_path, "data/gaoshu_demo.sqlite3")
        for folder_name, folder in folders.items():
            if not folder.exists():
                continue
            for file in folder.rglob("*"):
                if file.is_file():
                    zf.write(file, f"data/{folder_name}/{file.relative_to(folder).as_posix()}")
    return target


def restore_backup_zip(
    zip_bytes: bytes,
    *,
    root: Path,
    db_path: Path,
    folders: dict[str, Path],
    ensure_dirs,
    init_db,
) -> dict:
    """Restore a Sakura migration archive and keep a rollback copy of current data."""
    print(f"[migration] restore start: {len(zip_bytes)} bytes", flush=True)
    backup_root = root / "migration_backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    current_backup = backup_root / f"before_restore_{stamp}"
    current_backup.mkdir(parents=True, exist_ok=True)

    if db_path.exists():
        shutil.copy2(db_path, current_backup / db_path.name)
    for folder in folders.values():
        if folder.exists():
            shutil.copytree(folder, current_backup / folder.name, dirs_exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        archive_path = tmp_path / "backup.zip"
        archive_path.write_bytes(zip_bytes)
        with zipfile.ZipFile(archive_path) as zf:
            names = set(zf.namelist())
            print(f"[migration] archive entries: {len(names)}", flush=True)
            if "manifest.json" not in names or "data/gaoshu_demo.sqlite3" not in names:
                raise ValueError("这不是 Sakura 做题集完整迁移包：缺少 manifest 或数据库。")
            extract_root = (tmp_path / "extract").resolve()
            for member in zf.infolist():
                target = (extract_root / member.filename).resolve()
                if not str(target).startswith(str(extract_root)):
                    raise ValueError("迁移包路径不安全，已拒绝导入。")
            zf.extractall(extract_root)
            print("[migration] archive extracted", flush=True)

        extracted = tmp_path / "extract" / "data"
        ensure_dirs()
        shutil.copy2(extracted / "gaoshu_demo.sqlite3", db_path)
        print("[migration] database restored", flush=True)
        for name, target in folders.items():
            source = extracted / name
            if target.exists():
                shutil.rmtree(target)
            target.mkdir(parents=True, exist_ok=True)
            if source.exists():
                shutil.copytree(source, target, dirs_exist_ok=True)
            print(f"[migration] folder restored: {name}", flush=True)
    init_db()
    print("[migration] restore done", flush=True)
    return {"ok": True, "backup_path": str(current_backup)}
