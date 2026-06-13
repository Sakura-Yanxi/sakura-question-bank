from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent

SOURCE_PATTERNS = [
    "app.py",
    "notify_daily.py",
    "sakura/**/*.py",
    "static/index.html",
    "static/styles.css",
    "static/js/**/*.js",
]

EXCLUDE_PARTS = {
    "__pycache__",
    ".git",
    "gitdb",
    "data",
    "docs",
    "deploy",
    "tests",
}

PAGE_SIZE = 50
FRONT_PAGES = 30
BACK_PAGES = 30


def collect_files() -> list[Path]:
    files: list[Path] = []
    for pattern in SOURCE_PATTERNS:
        files.extend(ROOT.glob(pattern))
    clean: list[Path] = []
    seen: set[Path] = set()
    for path in files:
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if any(part in EXCLUDE_PARTS for part in rel.parts):
            continue
        if path in seen:
            continue
        seen.add(path)
        clean.append(path)
    return sorted(clean, key=lambda p: str(p.relative_to(ROOT)).lower())


def read_source_lines(path: Path) -> list[str]:
    rel = path.relative_to(ROOT).as_posix()
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = [f"/* ===== FILE: {rel} ===== */"]
    lines.extend(text.splitlines())
    lines.append("")
    return lines


def paginate(lines: list[str]) -> str:
    chunks = [lines[i : i + PAGE_SIZE] for i in range(0, len(lines), PAGE_SIZE)]
    output: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        output.append(f"===== 第 {index:02d} 页 / 共 {len(chunks):02d} 页 =====")
        output.extend(chunk)
        output.append("")
    return "\n".join(output)


def main() -> None:
    all_lines: list[str] = []
    for path in collect_files():
        all_lines.extend(read_source_lines(path))

    front_count = FRONT_PAGES * PAGE_SIZE
    back_count = BACK_PAGES * PAGE_SIZE
    if len(all_lines) <= front_count + back_count:
        selected = all_lines
    else:
        selected = all_lines[:front_count]
        selected.append("/* ===== 中间部分略去，以下为后 30 页源代码 ===== */")
        selected.extend(all_lines[-(back_count - 1) :])

    continuous = "\n".join(selected).strip() + "\n"
    paged = paginate(selected)

    (OUT_DIR / "04_源代码鉴别材料_连续代码.txt").write_text(continuous, encoding="utf-8")
    (OUT_DIR / "04_源代码鉴别材料_分页版.txt").write_text(paged, encoding="utf-8")

    print(f"source_files={len(collect_files())}")
    print(f"all_lines={len(all_lines)}")
    print(f"selected_lines={len(selected)}")
    print(f"paged_pages={(len(selected) + PAGE_SIZE - 1) // PAGE_SIZE}")


if __name__ == "__main__":
    main()
