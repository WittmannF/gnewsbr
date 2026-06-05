from __future__ import annotations

import hashlib


def content_hash(text: str) -> str:
    return "sha256-" + hashlib.sha256(text.encode()).hexdigest()
