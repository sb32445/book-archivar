from __future__ import annotations

from pathlib import Path

import chromadb

from book_archivar.chunking import Chunk

COLLECTION_NAME = "books"


class VectorStore:
    def __init__(self, chroma_dir: Path):
        self._client = chromadb.PersistentClient(path=str(chroma_dir))
        self._collection = self._client.get_or_create_collection(COLLECTION_NAME)

    def add_chunks(
        self,
        slug: str,
        book_title: str,
        chunks: list[Chunk],
        embeddings: list[list[float]],
    ) -> None:
        ids = [f"{slug}-{c.chunk_index}" for c in chunks]
        documents = [c.text for c in chunks]
        metadatas = [
            {"slug": slug, "book_title": book_title, "chapter_title": c.chapter_title,
             "chunk_index": c.chunk_index}
            for c in chunks
        ]
        self._collection.add(
            ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas
        )

    def delete_slug(self, slug: str) -> None:
        """Remove every chunk belonging to one book slug from the collection.

        Idempotent: deleting a slug with no stored chunks is a no-op.
        """
        self._collection.delete(where={"slug": slug})

    def query(
        self, query_embedding: list[float], top_k: int = 5, slug: str | None = None
    ) -> list[dict]:
        where = {"slug": slug} if slug else None
        result = self._collection.query(
            query_embeddings=[query_embedding], n_results=top_k, where=where
        )
        out = []
        for doc, meta, dist in zip(
            result["documents"][0], result["metadatas"][0], result["distances"][0]
        ):
            out.append(
                {
                    "slug": meta["slug"],
                    "book_title": meta["book_title"],
                    "chapter_title": meta["chapter_title"],
                    "chunk_index": meta["chunk_index"],
                    "text": doc,
                    "distance": dist,
                }
            )
        return out
