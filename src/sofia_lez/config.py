"""Configuration loading and path resolution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_config(path: str | Path) -> dict[str, Any]:
    """Load YAML and resolve configured paths relative to the repository root."""
    config_path = Path(path).expanduser().resolve()
    with config_path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}

    root = config_path.parent.parent
    config["_root"] = root
    for key, value in config.get("paths", {}).items():
        candidate = Path(value).expanduser()
        config["paths"][key] = candidate if candidate.is_absolute() else root / candidate
    return config


def ensure_parent(path: Path) -> Path:
    """Create a file's parent directory and return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
