"""Remember which embedding model built the index.

Vectors from different models (or dimensions) are not comparable, and Chroma
only complains with a cryptic dimension error, if at all. The stamp turns that
into a clear message that points to `book-archivar reindex`.
"""
from __future__ import annotations

import json

from book_archivar.config import Config


class EmbeddingMismatch(RuntimeError):
    pass


def read_stamp(config: Config) -> dict | None:
    path = config.data_dir / "embedding.json"
    return json.loads(path.read_text()) if path.exists() else None


def write_stamp(config: Config, dimensions: int | None) -> None:
    config.data_dir.mkdir(parents=True, exist_ok=True)
    (config.data_dir / "embedding.json").write_text(
        json.dumps({"model": config.embedding_model, "dimensions": dimensions}, indent=2)
    )


def problem(config: Config, dimensions: int | None = None) -> str | None:
    """Describe why the configured embedding setup does not fit the index, or None."""
    stamp = read_stamp(config)
    if stamp is None:
        return None
    if stamp["model"] != config.embedding_model:
        return (f"the index was built with embedding model '{stamp['model']}' but the config "
                f"says '{config.embedding_model}'")
    if dimensions and stamp.get("dimensions") and stamp["dimensions"] != dimensions:
        return (f"the embedding endpoint returns {dimensions}-dimensional vectors but the index "
                f"holds {stamp['dimensions']}-dimensional ones")
    return None


def verify_or_stamp(config: Config, dimensions: int | None) -> None:
    """Raise EmbeddingMismatch if the setup does not fit; stamp a fresh index."""
    message = problem(config, dimensions)
    if message:
        raise EmbeddingMismatch(f"{message}. Run `book-archivar reindex` to rebuild the index "
                                "with the configured model (or restore the old setting).")
    if read_stamp(config) is None:
        write_stamp(config, dimensions)
