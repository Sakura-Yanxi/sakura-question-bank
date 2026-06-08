from __future__ import annotations

import os
from pathlib import Path


def load_local_env(root: Path) -> None:
    """Load simple KEY=VALUE pairs from .env without adding a runtime dependency."""
    env_path = root / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lstrip("\ufeff")
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def write_local_env(root: Path, updates: dict[str, str]) -> None:
    """Update .env in place for local-only settings such as API keys."""
    env_path = root / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    seen = set()
    out = []
    for raw in lines:
        if "=" not in raw or raw.strip().startswith("#"):
            out.append(raw)
            continue
        key, _ = raw.split("=", 1)
        key = key.strip().lstrip("\ufeff")
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            out.append(raw)
    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}")
    env_path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
