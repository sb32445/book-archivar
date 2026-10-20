from __future__ import annotations

import dataclasses
import json
from pathlib import Path


@dataclasses.dataclass(frozen=True)
class BookEntry:
    slug: str
    title: str
    author: str
    language: str
    content_hash: str
    imported_at: str


def read_index(index_path: Path) -> list[BookEntry]:
    if not Path(index_path).exists():
        return []
    raw = json.loads(Path(index_path).read_text())
    return [BookEntry(**item) for item in raw]


def write_index(index_path: Path, entries: list[BookEntry]) -> None:
    Path(index_path).parent.mkdir(parents=True, exist_ok=True)
    Path(index_path).write_text(
        json.dumps([dataclasses.asdict(e) for e in entries], indent=2, ensure_ascii=False)
    )


def add_entry(index_path: Path, entry: BookEntry) -> None:
    entries = [e for e in read_index(index_path) if e.slug != entry.slug]
    entries.append(entry)
    write_index(index_path, entries)
