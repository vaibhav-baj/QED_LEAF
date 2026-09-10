"""Content-addressed, append-only files with integrity verification on every read."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .model import canonical, digest


class Store:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def put(self, kind: str, value: dict) -> str:
        identity = digest(value)
        directory = self.root / kind
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{identity}.json"
        try:
            with path.open("xb") as stream:
                stream.write(canonical(value))
        except FileExistsError:
            if self.get(kind, identity) != value:
                raise ValueError("Content-address collision")
        return identity

    def get(self, kind: str, identity: str) -> dict:
        if not re.fullmatch(r"[a-f0-9]{64}", identity):
            raise ValueError("Expected a SHA-256 object ID")
        path = self.root / kind / f"{identity}.json"
        if path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("Object exceeds size limit")
        value = json.loads(path.read_text(encoding="utf-8"))
        if digest(value) != identity:
            raise ValueError("Object integrity check failed")
        return value
