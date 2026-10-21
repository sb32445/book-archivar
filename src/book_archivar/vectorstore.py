from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import chromadb

from book_archivar.chunking import Chunk

COLLECTION_NAME = "books"
_TOKEN = re.compile(r"\w+", re.UNICODE)


class KeywordIndex:
    """SQLite FTS5 full-text index over the same chunks (BM25 ranking)."""

    def __init__(self, path: Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5("
            "slug UNINDEXED, book_title UNINDEXED, chapter_title UNINDEXED, "
            "chapter_index UNINDEXED, chunk_index UNINDEXED, text, "
            "tokenize='unicode61 remove_diacritics 2')"
        )

    def add_chunks(self, slug: str, book_title: str, chunks: list[Chunk]) -> None:
        self._db.executemany(
            "INSERT INTO chunks VALUES (?,?,?,?,?,?)",
            [(slug, book_title, c.chapter_title, c.chapter_index, c.chunk_index, c.text)
             for c in chunks],
        )
        self._db.commit()

    def delete_slug(self, slug: str) -> None:
        self._db.execute("DELETE FROM chunks WHERE slug = ?", (slug,))
        self._db.commit()

    def query(self, text: str, top_k: int = 5, slug: str | None = None) -> list[dict]:
        tokens = _TOKEN.findall(text)
        if not tokens:
            return []
        match = " OR ".join(f'"{t}"' for t in tokens)
        sql = ("SELECT slug, book_title, chapter_title, chapter_index, chunk_index, text "
               "FROM chunks WHERE chunks MATCH ?")
        args: list = [match]
        if slug:
            sql += " AND slug = ?"
            args.append(slug)
        sql += " ORDER BY bm25(chunks) LIMIT ?"
        args.append(top_k)
        return [
            {"slug": r[0], "book_title": r[1], "chapter_title": r[2],
             "chapter_index": r[3], "chunk_index": r[4], "text": r[5]}
            for r in self._db.execute(sql, args)
        ]

    def close(self) -> None:
        self._db.close()


class VectorStore:
    """Chroma for semantic search, plus (optionally) a keyword index kept in
    step with it so hybrid search can combine both."""

    def __init__(self, chroma_dir: Path, keyword_db: Path | None = None):
        self._client = chromadb.PersistentClient(path=str(chroma_dir))
        self._collection = self._client.get_or_create_collection(COLLECTION_NAME)
        self.keyword: KeywordIndex | None = KeywordIndex(keyword_db) if keyword_db else None

    def add_chunks(
        self,
        slug: str,
        book_title: str,
        chunks: list[Chunk],
        embeddings: list[list[float]],
    ) -> None:
        if not chunks:
            return
        self._collection.add(
            ids=[f"{slug}-{c.chunk_index}" for c in chunks],
            embeddings=embeddings,
            documents=[c.text for c in chunks],
            metadatas=[
                {"slug": slug, "book_title": book_title, "chapter_title": c.chapter_title,
                 "chapter_index": c.chapter_index, "chunk_index": c.chunk_index}
                for c in chunks
            ],
        )
        if self.keyword:
            self.keyword.add_chunks(slug, book_title, chunks)

    def delete_slug(self, slug: str) -> None:
        """Remove every chunk of one book. Idempotent."""
        self._collection.delete(where={"slug": slug})
        if self.keyword:
            self.keyword.delete_slug(slug)

    def count(self) -> int:
        return self._collection.count()

    def query(
        self, query_embedding: list[float], top_k: int = 5, slug: str | None = None
    ) -> list[dict]:
        where = {"slug": slug} if slug else None
        result = self._collection.query(
            query_embeddings=[query_embedding], n_results=top_k, where=where
        )
        return [
            {
                "slug": meta["slug"],
                "book_title": meta["book_title"],
                "chapter_title": meta["chapter_title"],
                "chapter_index": meta.get("chapter_index"),
                "chunk_index": meta["chunk_index"],
                "text": doc,
                "distance": dist,
            }
            for doc, meta, dist in zip(
                result["documents"][0], result["metadatas"][0], result["distances"][0]
            )
        ]

    def keyword_query(self, text: str, top_k: int = 5, slug: str | None = None) -> list[dict]:
        return self.keyword.query(text, top_k, slug) if self.keyword else []
