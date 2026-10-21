from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path
from typing import Callable

from chromadb.api.shared_system_client import SharedSystemClient

from book_archivar.chapters import read_chapters
from book_archivar.chunking import chunk_book
from book_archivar.config import Config
from book_archivar.importer import embed_chunks
from book_archivar.library import read_index
from book_archivar.stamp import write_stamp
from book_archivar.vectorstore import VectorStore

logger = logging.getLogger(__name__)


def reindex(config: Config, embeddings_client, progress: Callable[[str], None] = lambda m: None) -> int:
    """Rebuild the search indexes (Chroma + keyword) from library/ alone.

    Use it after changing the embedding model or chunk settings, or when the
    index is damaged. The new index is built next to the old one and swapped in
    only when everything succeeded; the old one is kept as `*.old-<timestamp>`
    (delete it when you are happy). Stop `serve` while this runs.
    """
    entries = read_index(config.library_dir / "index.json")
    new_chroma = config.data_dir / "chroma.new"
    new_keyword = config.data_dir / "keyword.db.new"
    shutil.rmtree(new_chroma, ignore_errors=True)
    new_keyword.unlink(missing_ok=True)

    store = VectorStore(new_chroma, new_keyword)
    dimensions = None
    chunk_total = 0
    for n, entry in enumerate(entries, 1):
        book_dir = config.library_dir / entry.slug
        chapters = read_chapters(book_dir / "chapters.json")
        chunks = chunk_book(
            (book_dir / "book.md").read_bytes(), chapters, config.chunk_size, config.chunk_overlap
        )
        embeddings = embed_chunks(embeddings_client, chunks)
        if embeddings:
            dimensions = len(embeddings[0])
        store.add_chunks(entry.slug, entry.title, chunks, embeddings)
        chunk_total += len(chunks)
        progress(f"[{n}/{len(entries)}] {entry.slug}: {len(chunks)} chunks")

    store.keyword.close()
    del store
    SharedSystemClient.clear_system_cache()

    stamp = int(time.time())
    for current, new in ((config.chroma_dir, new_chroma), (config.keyword_db, new_keyword)):
        if current.exists():
            current.rename(current.with_name(f"{current.name}.old-{stamp}"))
        new.rename(current)
    write_stamp(config, dimensions)
    logger.info("reindexed %d books, %d chunks", len(entries), chunk_total)
    return chunk_total
