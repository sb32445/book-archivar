from __future__ import annotations

from book_archivar.vectorstore import VectorStore

RRF_K = 60  # reciprocal-rank-fusion constant
# Keyword hits count less than semantic ones: on a natural-language question the
# BM25 leg mostly matches common words, while it is decisive for names and quotes
# (those are found by both legs and rise to the top anyway).
WEIGHTS = {"semantic": 1.0, "keyword": 0.6}
MODES = ("hybrid", "semantic", "keyword")


def search(
    embeddings_client,
    store: VectorStore,
    query: str,
    slug: str | None = None,
    top_k: int = 5,
    mode: str = "hybrid",
) -> list[dict]:
    """Semantic (vectors), keyword (BM25) or hybrid search.

    Hybrid fuses both rankings with reciprocal rank fusion: names and quotes
    that vectors miss are found by keywords, paraphrases by vectors. Without a
    keyword index it silently degrades to semantic search.
    """
    if mode not in MODES:
        raise ValueError(f"unknown mode '{mode}', expected one of {MODES}")
    if mode == "keyword":
        return store.keyword_query(query, top_k, slug)
    if mode == "semantic" or store.keyword is None:
        return store.query(embeddings_client.embed([query])[0], top_k, slug)

    pool = max(top_k * 3, 10)
    semantic = store.query(embeddings_client.embed([query])[0], pool, slug)
    keyword = store.keyword_query(query, pool, slug)

    fused: dict[tuple, dict] = {}
    for source, hits in (("semantic", semantic), ("keyword", keyword)):
        for rank, hit in enumerate(hits):
            key = (hit["slug"], hit["chunk_index"])
            entry = fused.setdefault(key, {**hit, "score": 0.0, "sources": []})
            entry["score"] += WEIGHTS[source] / (RRF_K + rank + 1)
            entry["sources"].append(source)
            entry.setdefault("distance", hit.get("distance"))
    return sorted(fused.values(), key=lambda h: -h["score"])[:top_k]
