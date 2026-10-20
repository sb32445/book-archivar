import shutil
from pathlib import Path

import pytest

from book_archivar.config import Config

FIXTURES = Path(__file__).parent / "fixtures"


class FakeEmbeddings:
    """Deterministic stand-in for the embedding endpoint (3 dimensions)."""

    def embed(self, texts):
        return [[float(len(t) % 7), float(len(t) % 11), 1.0] for t in texts]


@pytest.fixture
def alice_epub(tmp_path) -> Path:
    dest = tmp_path / "alice.epub"
    shutil.copy(FIXTURES / "alice.epub", dest)
    return dest


@pytest.fixture
def config(tmp_path) -> Config:
    return Config(data_dir=tmp_path / "data", chunk_size=500, chunk_overlap=50)


@pytest.fixture
def embeddings():
    return FakeEmbeddings()
