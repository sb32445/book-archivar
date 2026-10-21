"""Add-on: catch "same book, different file" before it lands in the library.

The core only rejects byte-identical files. With this add-on enabled, an EPUB
whose author and title match an existing book (after normalisation) but whose
bytes differ is parked in review/ for a human decision instead of being
imported. Resolve entries with `book-archivar review ...`.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from book_archivar.hashing import normalize_author_title
from book_archivar.library import BookEntry


def find_fuzzy_duplicate(author: str, title: str, entries: list[BookEntry]) -> BookEntry | None:
    wanted = normalize_author_title(author, title)
    return next(
        (e for e in entries if normalize_author_title(e.author, e.title) == wanted), None
    )


def file_for_review(
    epub_path: Path, review_dir: Path, content_hash: str, matched: BookEntry
) -> Path:
    """Copy the candidate into review/<matched-slug>-<hash8>/ (the source file
    is left alone, like everywhere else)."""
    folder = Path(review_dir) / f"{matched.slug}-{content_hash[:8]}"
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy2(epub_path, folder / epub_path.name)
    (folder / "note.json").write_text(
        json.dumps(
            {
                "matched_slug": matched.slug,
                "matched_title": matched.title,
                "reason": "author+title match, different content hash",
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return folder
