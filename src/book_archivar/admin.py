"""Library maintenance: remove a book, check the setup."""
from __future__ import annotations

import shutil
import urllib.error

from book_archivar import stamp
from book_archivar.config import Config
from book_archivar.library import read_index, remove_entry
from book_archivar.vectorstore import VectorStore


def remove_book(config: Config, store: VectorStore, slug: str) -> bool:
    """Delete a book from the library, the index and both search indexes."""
    index_path = config.library_dir / "index.json"
    if slug not in {e.slug for e in read_index(index_path)}:
        return False
    shutil.rmtree(config.library_dir / slug, ignore_errors=True)
    store.delete_slug(slug)
    remove_entry(index_path, slug)
    return True


def doctor(config: Config, embeddings_client, store: VectorStore | None = None) -> list[tuple[str, bool, str]]:
    """Run the setup checks; returns (check, ok, detail) rows."""
    rows: list[tuple[str, bool, str]] = []
    dimensions = None
    try:
        dimensions = len(embeddings_client.embed(["test"])[0])
        rows.append(("embedding endpoint", True,
                     f"{config.embedding_base_url} model={config.embedding_model} "
                     f"dimensions={dimensions}"))
    except (OSError, urllib.error.URLError, KeyError, IndexError, ValueError) as exc:
        rows.append(("embedding endpoint", False,
                     f"{config.embedding_base_url}: {exc} (is the server running, is the "
                     f"model '{config.embedding_model}' loaded?)"))

    problem = stamp.problem(config, dimensions)
    rows.append(("index matches embedding setup", problem is None,
                 problem or "ok" + ("" if stamp.read_stamp(config) else " (no index yet)")))

    books = read_index(config.library_dir / "index.json")
    rows.append(("library", True, f"{len(books)} books in {config.library_dir}"))
    if store is not None:
        rows.append(("vector index", True, f"{store.count()} chunks"))
        rows.append(("keyword index", store.keyword is not None,
                     "enabled" if store.keyword else "disabled: hybrid search falls back to semantic"))

    from book_archivar.converters import supported_suffixes
    rows.append(("formats", True, ", ".join(sorted(supported_suffixes(config)))))
    return rows
