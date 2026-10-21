from __future__ import annotations

import hashlib
import re
from pathlib import Path

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_EDITION_SUFFIX_RE = re.compile(
    r"[:,]?\s*(\d+\.?\s*(auflage|edition)|(revised|updated)\s*edition)\s*$", re.IGNORECASE
)
_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


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


def _normalize_one(value: str) -> str:
    value = _EDITION_SUFFIX_RE.sub("", value)
    if "," in value:  # "Lastname, Firstname" -> "Firstname Lastname"
        last, _, first = value.partition(",")
        value = f"{first.strip()} {last.strip()}"
    return _WS_RE.sub(" ", _PUNCT_RE.sub(" ", value.lower())).strip()


def normalize_author_title(author: str, title: str) -> tuple[str, str]:
    """Comparison form for duplicate matching (not for display)."""
    return _normalize_one(author), _normalize_one(title)
