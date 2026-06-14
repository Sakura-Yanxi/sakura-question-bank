from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

DEFAULT_UPDATE_REPO = "Sakura-Yanxi/sakura-question-bank"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update Sakura from GitHub Releases while keeping local data.")
    parser.add_argument("--root", default="", help="Project root. Defaults to the parent folder of this script.")
    parser.add_argument("--repo", default="", help="GitHub owner/repo. Defaults to SAKURA_UPDATE_REPO or Sakura upstream.")
    parser.add_argument("--current-version", default="", help="Current version override, mainly for tests.")
    parser.add_argument("--pause", action="store_true", help="Wait for Enter before exiting, useful when double-clicked.")
    return parser.parse_args(argv)


def project_root(args: argparse.Namespace) -> Path:
    if args.root:
        return Path(args.root).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def load_update_runtime(root: Path):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from sakura import __version__ as app_version
    from sakura.core import config as sakura_config
    from sakura.system import update as sakura_update

    sakura_config.load_local_env(root, override_keys={"SAKURA_UPDATE_REPO"})
    return app_version, sakura_update


def print_step(step: dict) -> None:
    mark = "OK" if step.get("ok") else "FAIL"
    name = step.get("name", "步骤")
    print(f"[{mark}] {name}")
    output = str(step.get("output") or "").strip()
    if output:
        print(output)


def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = project_root(args)
    app_version, sakura_update = load_update_runtime(root)
    current_version = args.current_version or app_version
    repo = args.repo or os.getenv("SAKURA_UPDATE_REPO", "").strip() or DEFAULT_UPDATE_REPO

    print("== Sakura 轻量更新器 ==")
    print(f"项目目录：{root}")
    print(f"当前版本：{current_version}")
    print(f"更新仓库：{repo}")
    print("会保留 data/、.env、.venv 和本地私有版权材料。")
    print()

    result = sakura_update.apply_update(root, current_version, repo)
    for step in result.get("steps") or []:
        print_step(step)
        print()

    if result.get("backup"):
        print(f"旧代码备份：{result['backup']}")

    if result.get("ok"):
        print(result.get("message") or "更新完成。")
        if result.get("restart_required"):
            print("请重新启动 Sakura 服务。")
        return 0

    print(result.get("error") or "更新失败。")
    release_url = (result.get("info") or {}).get("url") or (result.get("info") or {}).get("releases_url")
    if release_url:
        print(f"手动下载地址：{release_url}")
    return 1


def main() -> None:
    args = parse_args()
    code = 1
    try:
        code = run(sys.argv[1:])
    except KeyboardInterrupt:
        print("已取消更新。")
        code = 130
    except Exception as exc:
        print(f"更新器异常：{exc}")
        code = 1
    finally:
        if args.pause:
            try:
                input("\n按 Enter 退出...")
            except EOFError:
                pass
    raise SystemExit(code)


if __name__ == "__main__":
    main()
