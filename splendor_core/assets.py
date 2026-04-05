"""Helpers for reading bundled assets and manifests."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def _asset_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "splendor_app" / "assets"

    package_root = Path(__file__).resolve().parent
    candidate_roots = (
        package_root / "assets",
        package_root.parent / "splendor_app" / "assets",
    )
    for candidate in candidate_roots:
        if candidate.is_dir():
            return candidate
    return candidate_roots[-1]


def asset_root() -> Path:
    return _asset_root()


def load_asset_bytes(*parts: str) -> bytes | None:
    resource = _asset_root().joinpath(*parts)
    if not resource.is_file():
        return None
    return resource.read_bytes()


def load_json_asset(*parts: str) -> Any:
    resource = _asset_root().joinpath(*parts)
    if not resource.is_file():
        joined_path = "/".join(parts)
        raise FileNotFoundError(f"Missing bundled asset: {joined_path}")
    return json.loads(resource.read_text(encoding="utf-8"))
