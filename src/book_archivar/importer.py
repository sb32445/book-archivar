from __future__ import annotations

import dataclasses
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from book_archivar.addons.duplicates import file_for_review, find_fuzzy_duplicate
from book_archivar.chapters import write_chapters
from book_archivar.chunking import chunk_book
from book_archivar.config import Config
from book_archivar.epub_convert import convert_epub
from book_archivar.hashing import canonical_author, sha256_file, slugify
from book_archivar.library import BookEntry, add_entry, read_index
from book_archivar.vectorstore import VectorStore

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 20


@dataclasses.dataclass(frozen=True)
class ImportOutcome:
    status: str  # "imported" | "duplicate" | "review"
    slug: str


def _unique_slug(base: str, content_hash: str, taken: set[str]) -> str:
    """Plain author-title slug; if taken by a different file, add the hash."""
    if base not in taken:
        return base
    candidate = f"{base}-{content_hash[:8]}"
    suffix = 2
    while candidate in taken:
        candidate = f"{base}-{content_hash[:8]}-{suffix}"
        suffix += 1
    return candidate


def import_epub(
    epub_path: Path,
    config: Config,
    embeddings_client,
    vector_store: VectorStore,
    review_dir: Path | None = None,
    force: bool = False,
) -> ImportOutcome:
    """Import one EPUB into <data_dir>/library/<slug>/ and index it in Chroma.

    The same file (by SHA-256) is never imported twice. Embedding happens before
    anything is written, so an unreachable embedding endpoint leaves no
    half-imported book behind. The source file is left untouched.

    With `review_dir` (duplicates add-on), a book whose author+title match an
    existing one but whose bytes differ is copied there for a human decision
    instead of being imported. `force=True` skips both duplicate checks.
    """
    index_path = config.library_dir / "index.json"
    content_hash = sha256_file(epub_path)
    entries = read_index(index_path)
    if not force:
        for entry in entries:
            if entry.content_hash == content_hash:
                return ImportOutcome("duplicate", entry.slug)

    book = convert_epub(epub_path)
    author = canonical_author(book.author)
    if review_dir is not None and not force:
        matched = find_fuzzy_duplicate(author, book.title, entries)
        if matched is not None:
            file_for_review(epub_path, review_dir, content_hash, matched)
            logger.info("%s looks like %s: filed for review", epub_path.name, matched.slug)
            return ImportOutcome("review", matched.slug)
    slug = _unique_slug(slugify(author, book.title), content_hash, {e.slug for e in entries})

    body = book.markdown.encode("utf-8")
    chunks = chunk_book(body, book.chapters, config.chunk_size, config.chunk_overlap)
    embeddings: list[list[float]] = []
    for start in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[start : start + EMBED_BATCH_SIZE]
        embeddings.extend(embeddings_client.embed([c.text for c in batch]))

    book_dir = config.library_dir / slug
    book_dir.mkdir(parents=True, exist_ok=True)
    (book_dir / "book.md").write_bytes(body)
    write_chapters(book.chapters, book_dir / "chapters.json")

    vector_store.delete_slug(slug)  # Chroma's add() silently ignores existing ids
    vector_store.add_chunks(slug, book.title, chunks, embeddings)

    imported_at = datetime.now(timezone.utc).isoformat()
    (book_dir / "metadata.json").write_text(
        json.dumps(
            {
                "title": book.title,
                "author": author,
                "language": book.language,
                "content_hash": content_hash,
                "imported_at": imported_at,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    add_entry(
        index_path,
        BookEntry(slug, book.title, author, book.language, content_hash, imported_at),
    )
    logger.info("imported %s as %s (%d chapters, %d chunks)",
                epub_path.name, slug, len(book.chapters), len(chunks))
    return ImportOutcome("imported", slug)
