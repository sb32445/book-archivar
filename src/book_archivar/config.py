from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_DATA_DIR = "~/.local/share/book-archivar"


@dataclass(frozen=True)
class Config:
    data_dir: Path = Path(DEFAULT_DATA_DIR).expanduser()
    embedding_base_url: str = "http://localhost:11434/v1"
    embedding_model: str = "bge-m3"
    embedding_api_key: str = "not-needed"
    chunk_size: int = 1500
    chunk_overlap: int = 200

    @property
    def library_dir(self) -> Path:
        return self.data_dir / "library"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"


def load_config(path: Path | None = None) -> Config:
    """Load config from `path`, $BOOK_ARCHIVAR_CONFIG, or ./config.yaml, in that
    order. With none of them present, the defaults apply."""
    if path is None and os.environ.get("BOOK_ARCHIVAR_CONFIG"):
        path = Path(os.environ["BOOK_ARCHIVAR_CONFIG"])
    if path is None and Path("config.yaml").exists():
        path = Path("config.yaml")
    if path is None:
        return Config()

    raw = yaml.safe_load(Path(path).read_text()) or {}
    defaults = Config()
    return Config(
        data_dir=Path(raw.get("data_dir", defaults.data_dir)).expanduser(),
        embedding_base_url=raw.get("embedding_base_url", defaults.embedding_base_url),
        embedding_model=raw.get("embedding_model", defaults.embedding_model),
        embedding_api_key=raw.get("embedding_api_key", defaults.embedding_api_key),
        chunk_size=int(raw.get("chunk_size", defaults.chunk_size)),
        chunk_overlap=int(raw.get("chunk_overlap", defaults.chunk_overlap)),
    )
