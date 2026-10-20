import json

from book_archivar.importer import import_epub
from book_archivar.library import read_index
from book_archivar.mcp_server import get_chapter, list_books, list_chapters
from book_archivar.vectorstore import VectorStore
from tests.helpers import make_epub


def test_import_then_read_back(alice_epub, config, embeddings):
    store = VectorStore(config.chroma_dir)
    outcome = import_epub(alice_epub, config, embeddings, store)
    assert outcome.status == "imported"
    assert alice_epub.exists()  # source file is never deleted

    book_dir = config.library_dir / outcome.slug
    assert json.loads((book_dir / "metadata.json").read_text())["author"] == "Lewis Carroll"
    assert list_books(config)[0]["slug"] == outcome.slug

    chapters = list_chapters(config, outcome.slug)
    assert len(chapters) >= 10
    assert "Alice" in get_chapter(config, outcome.slug, "1")
    assert get_chapter(config, outcome.slug, chapters[2]["title"]) == get_chapter(
        config, outcome.slug, "2"
    )

    hits = store.query(embeddings.embed(["rabbit"])[0], top_k=3, slug=outcome.slug)
    assert hits and hits[0]["slug"] == outcome.slug


def test_same_file_twice_is_a_duplicate(alice_epub, config, embeddings):
    store = VectorStore(config.chroma_dir)
    first = import_epub(alice_epub, config, embeddings, store)
    second = import_epub(alice_epub, config, embeddings, store)
    assert (second.status, second.slug) == ("duplicate", first.slug)
    assert len(read_index(config.library_dir / "index.json")) == 1


def test_same_title_different_file_gets_distinct_slug(tmp_path, config, embeddings):
    store = VectorStore(config.chroma_dir)
    a = import_epub(make_epub(tmp_path / "a.epub"), config, embeddings, store)
    b = import_epub(make_epub(tmp_path / "b.epub", single_file=True), config, embeddings, store)
    assert a.slug == "jane-doe-test-book"
    assert b.slug.startswith("jane-doe-test-book-") and b.slug != a.slug


def test_failing_embeddings_leave_no_trace(alice_epub, config):
    class Broken:
        def embed(self, texts):
            raise ConnectionError("endpoint down")

    store = VectorStore(config.chroma_dir)
    try:
        import_epub(alice_epub, config, Broken(), store)
    except ConnectionError:
        pass
    assert not config.library_dir.exists() or not any(config.library_dir.iterdir())


def test_unknown_book_and_chapter_messages(config):
    assert "not found" in list_chapters(config, "nope")
    assert "not found" in get_chapter(config, "nope", "0")


def test_whitespace_only_chunks_are_skipped():
    from book_archivar.chapters import Chapter
    from book_archivar.chunking import chunk_book

    body = b"\n\n\n\n" + b"word " * 20
    chunks = chunk_book(body, [Chapter("c", 0, len(body))], size=4, overlap=0)
    assert chunks and all(c.text.strip() for c in chunks)
