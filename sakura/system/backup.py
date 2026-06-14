from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path


def _query_first(query: dict, key: str, default: str = "") -> str:
    values = query.get(key) or [default]
    return str(values[0] if values else default)


def export_options_from_query(query: dict, now: datetime | None = None) -> dict:
    mode = _query_first(query, "mode", "full")
    if mode not in {"full", "light", "range"}:
        raise ValueError("导出模式必须是 full、light 或 range")
    start_date = _query_first(query, "start_date").strip()
    end_date = _query_first(query, "end_date").strip()
    include_assets = _query_first(query, "include_assets", "1" if mode == "full" else "0") == "1"
    if mode == "light":
        include_assets = False
        start_date = ""
        end_date = ""
    if mode == "range" and (not start_date or not end_date):
        raise ValueError("范围导出必须填写开始日期和结束日期")
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    suffix = mode if mode != "range" else f"range_{start_date}_to_{end_date}"
    return {
        "mode": mode,
        "start_date": start_date,
        "end_date": end_date,
        "include_assets": include_assets,
        "filename": f"sakura_backup_{suffix}_{stamp}.zip",
    }


def build_backup_export_file(
    query: dict,
    db_path: Path,
    folders: dict[str, Path],
    now: datetime | None = None,
) -> tuple[Path, str]:
    export_options = export_options_from_query(query, now)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
        tmp_path = Path(tmp.name)
    try:
        build_backup_zip_file(
            tmp_path,
            db_path,
            folders,
            include_assets=export_options["include_assets"],
            start_date=export_options["start_date"],
            end_date=export_options["end_date"],
        )
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    return tmp_path, export_options["filename"]


def _safe_date(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text[:10]).date().isoformat()
    except ValueError as exc:
        raise ValueError("日期格式必须是 YYYY-MM-DD") from exc


def _date_clause(columns: list[str]) -> str:
    return " OR ".join(f"({col} IS NOT NULL AND date({col}) BETWEEN date(?) AND date(?))" for col in columns)


def _date_params(columns: list[str], start_date: str, end_date: str) -> list[str]:
    params: list[str] = []
    for _ in columns:
        params.extend([start_date, end_date])
    return params


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table,)).fetchone()
    return bool(row)


def _prune_by_date(conn: sqlite3.Connection, start_date: str, end_date: str) -> None:
    """Prune a copied Sakura database to records touched in the given date range."""
    if _table_exists(conn, "documents"):
        doc_cols = ["created_at"]
        doc_clause = _date_clause(doc_cols)
        question_cols = ["created_at", "last_reviewed_at", "mastered_at"]
        question_clause = _date_clause(question_cols)
        doc_params = _date_params(doc_cols, start_date, end_date)
        q_params = _date_params(question_cols, start_date, end_date)
        conn.execute(
            f"""
            CREATE TEMP TABLE keep_documents AS
            SELECT id FROM documents WHERE {doc_clause}
            UNION
            SELECT document_id FROM questions WHERE {question_clause}
            """,
            [*doc_params, *q_params],
        )
        conn.execute("DELETE FROM questions WHERE document_id NOT IN (SELECT id FROM keep_documents)")
        conn.execute("DELETE FROM documents WHERE id NOT IN (SELECT id FROM keep_documents)")
        if _table_exists(conn, "insights"):
            conn.execute("DELETE FROM insights WHERE question_id NOT IN (SELECT id FROM questions)")

    if _table_exists(conn, "textbooks"):
        textbook_cols = ["created_at"]
        page_cols = ["created_at"]
        chat_cols = ["created_at"]
        conn.execute(
            f"""
            CREATE TEMP TABLE keep_textbooks AS
            SELECT id FROM textbooks WHERE {_date_clause(textbook_cols)}
            UNION
            SELECT textbook_id FROM textbook_pages WHERE {_date_clause(page_cols)}
            UNION
            SELECT textbook_id FROM textbook_chats WHERE {_date_clause(chat_cols)}
            """,
            [
                *_date_params(textbook_cols, start_date, end_date),
                *_date_params(page_cols, start_date, end_date),
                *_date_params(chat_cols, start_date, end_date),
            ],
        )
        conn.execute("DELETE FROM textbook_pages WHERE textbook_id NOT IN (SELECT id FROM keep_textbooks)")
        conn.execute("DELETE FROM textbook_chats WHERE textbook_id NOT IN (SELECT id FROM keep_textbooks)")
        conn.execute("DELETE FROM textbooks WHERE id NOT IN (SELECT id FROM keep_textbooks)")

    ranged_tables = {
        "ai_teacher_turns": ["created_at"],
        "checkins": ["day", "created_at"],
        "daily_rules": ["created_at", "updated_at"],
        "learner_profile": ["created_at"],
        "mentor_experience": ["created_at"],
        "question_review_notes": ["created_at"],
        "reflections": ["period_start", "period_end", "created_at"],
        "teacher_memory": ["created_at"],
    }
    for table, columns in ranged_tables.items():
        if _table_exists(conn, table):
            conn.execute(
                f"DELETE FROM {table} WHERE NOT ({_date_clause(columns)})",
                _date_params(columns, start_date, end_date),
            )

    if _table_exists(conn, "practice_batches"):
        batch_cols = ["day", "created_at", "completed_at"]
        conn.execute(
            f"DELETE FROM practice_batches WHERE NOT ({_date_clause(batch_cols)})",
            _date_params(batch_cols, start_date, end_date),
        )
    if _table_exists(conn, "practice_batch_items"):
        conn.execute(
            """
            DELETE FROM practice_batch_items
            WHERE batch_id NOT IN (SELECT id FROM practice_batches)
               OR question_id NOT IN (SELECT id FROM questions)
            """
        )
    if _table_exists(conn, "question_review_notes"):
        conn.execute(
            """
            DELETE FROM question_review_notes
            WHERE question_id NOT IN (SELECT id FROM questions)
            """
        )


def _prepare_database_for_export(db_path: Path, tmp_dir: Path, start_date: str = "", end_date: str = "") -> Path:
    export_db = tmp_dir / "gaoshu_demo.sqlite3"
    if db_path.exists():
        shutil.copy2(db_path, export_db)
    else:
        export_db.touch()
    if start_date or end_date:
        if not start_date or not end_date:
            raise ValueError("按日期范围导出时必须同时填写开始日期和结束日期")
        if start_date > end_date:
            raise ValueError("开始日期不能晚于结束日期")
        conn = sqlite3.connect(export_db)
        try:
            _prune_by_date(conn, start_date, end_date)
            conn.commit()
            conn.execute("VACUUM")
        finally:
            conn.close()
    return export_db


def _collect_referenced_asset_paths(db_path: Path) -> set[Path]:
    paths: set[Path] = set()
    if not db_path.exists():
        return paths
    conn = sqlite3.connect(db_path)
    try:
        for table, column in (
            ("documents", "stored_path"),
            ("questions", "image_path"),
            ("textbooks", "stored_path"),
            ("textbook_pages", "image_path"),
        ):
            if not _table_exists(conn, table):
                continue
            for (value,) in conn.execute(f"SELECT {column} FROM {table} WHERE COALESCE({column}, '') <> ''"):
                try:
                    paths.add(Path(value))
                except TypeError:
                    pass
    finally:
        conn.close()
    return paths


def _archive_name_for_asset(path: Path, folders: dict[str, Path]) -> str | None:
    try:
        resolved = path.resolve()
    except OSError:
        return None
    for folder_name, folder in folders.items():
        try:
            rel = resolved.relative_to(folder.resolve())
        except ValueError:
            continue
        return f"data/{folder_name}/{rel.as_posix()}"
    return None


def build_backup_zip_file(
    target: Path,
    db_path: Path,
    folders: dict[str, Path],
    *,
    include_assets: bool = True,
    start_date: str = "",
    end_date: str = "",
) -> Path:
    """Build a Sakura migration archive containing database and generated assets."""
    start_date = _safe_date(start_date)
    end_date = _safe_date(end_date)
    manifest = {
        "app": "Sakura做题集",
        "version": 1,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "range" if start_date or end_date else ("full" if include_assets else "light"),
        "start_date": start_date,
        "end_date": end_date,
        "includes": ["database", *list(folders.keys())] if include_assets else ["database"],
    }
    with tempfile.TemporaryDirectory() as tmp:
        export_db = _prepare_database_for_export(db_path, Path(tmp), start_date, end_date)
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            zf.write(export_db, "data/gaoshu_demo.sqlite3")
            if include_assets:
                if start_date or end_date:
                    asset_paths = _collect_referenced_asset_paths(export_db)
                    for file in sorted(asset_paths, key=lambda p: str(p)):
                        archive_name = _archive_name_for_asset(file, folders)
                        if archive_name and file.exists() and file.is_file():
                            zf.write(file, archive_name)
                else:
                    for folder_name, folder in folders.items():
                        if not folder.exists():
                            continue
                        for file in folder.rglob("*"):
                            if file.is_file():
                                zf.write(file, f"data/{folder_name}/{file.relative_to(folder).as_posix()}")
    return target


def _relocate_asset_path(old: str, target_dir: Path) -> str:
    """Re-anchor a stored asset path onto this machine's data dir, keeping the file name.
    Handles both Windows ('\\') and POSIX ('/') separators from the source machine."""
    if not old:
        return old
    name = Path(str(old).replace("\\", "/")).name
    if not name:
        return old
    return str(target_dir / name)


def rewrite_asset_paths(db_path: Path, *, uploads_dir: Path, pages_dir: Path) -> dict:
    """After a restore, the copied DB still holds the SOURCE machine's absolute asset paths.
    Re-anchor them onto this machine's upload/page dirs (matched by file name) so images
    resolve here and to_public_path()'s relative_to(ROOT) no longer raises ValueError."""
    mapping = [
        ("documents", "stored_path", uploads_dir),
        ("textbooks", "stored_path", uploads_dir),
        ("questions", "image_path", pages_dir),
        ("textbook_pages", "image_path", pages_dir),
    ]
    counts: dict[str, int] = {}
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        for table, column, target_dir in mapping:
            if target_dir is None or not _table_exists(conn, table):
                continue
            rows = conn.execute(
                f"SELECT id, {column} value FROM {table} WHERE {column} IS NOT NULL AND {column} <> ''"
            ).fetchall()
            updated = 0
            for row in rows:
                new_value = _relocate_asset_path(row["value"], target_dir)
                if new_value != row["value"]:
                    conn.execute(f"UPDATE {table} SET {column} = ? WHERE id = ?", (new_value, row["id"]))
                    updated += 1
            counts[f"{table}.{column}"] = updated
        conn.commit()
    finally:
        conn.close()
    return counts


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
            try:
                manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ValueError("迁移包 manifest 解析失败。") from exc
            included = set(manifest.get("includes") or [])
            extract_root = (tmp_path / "extract").resolve()
            for member in zf.infolist():
                target = (extract_root / member.filename).resolve()
                try:
                    target.relative_to(extract_root)
                except ValueError:
                    raise ValueError("迁移包路径不安全，已拒绝导入。")
            zf.extractall(extract_root)
            print("[migration] archive extracted", flush=True)

        extracted = tmp_path / "extract" / "data"
        ensure_dirs()
        shutil.copy2(extracted / "gaoshu_demo.sqlite3", db_path)
        print("[migration] database restored", flush=True)
        for name, target in folders.items():
            if name not in included:
                print(f"[migration] folder preserved: {name}", flush=True)
                continue
            source = extracted / name
            if target.exists():
                shutil.rmtree(target)
            target.mkdir(parents=True, exist_ok=True)
            if source.exists():
                shutil.copytree(source, target, dirs_exist_ok=True)
            print(f"[migration] folder restored: {name}", flush=True)
    init_db()
    rewritten = rewrite_asset_paths(
        db_path,
        uploads_dir=folders.get("uploads"),
        pages_dir=folders.get("pages"),
    )
    print(f"[migration] asset paths re-anchored: {rewritten}", flush=True)
    print("[migration] restore done", flush=True)
    return {"ok": True, "backup_path": str(current_backup), "rewritten_paths": rewritten}
