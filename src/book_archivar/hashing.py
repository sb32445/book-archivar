from __future__ import annotations

import hashlib
import re
from pathlib import Path

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_author(author: str) -> str:
    """Rewrite "Lastname, Firstname" to "Firstname Lastname", case preserved."""
    author = author.strip()
    if "," not in author:
        return author
    last, _, first = author.partition(",")
    last, first = last.strip(), first.strip()
    return f"{first} {last}" if last and first else author


def slugify(author: str, title: str) -> str:
    return _SLUG_RE.sub("-", f"{author}-{title}".lower()).strip("-") or "book"
