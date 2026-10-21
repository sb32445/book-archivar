import shutil

import pytest

from book_archivar import admin, cli, stamp
from book_archivar.chapters import Chapter
from book_archivar.chunking import chunk_book
from book_archivar.converters import ConversionError, convert, convert_text, supported_suffixes
from book_archivar.importer import import_book
from book_archivar.library import read_index
from book_archivar.mcp_server import get_book_info, get_chapter
from book_archivar.reindex import reindex
from book_archivar.search import search
from book_archivar.vectorstore import VectorStore
from tests.helpers import make_epub


# ---------- chunking ----------
def test_chunks_end_at_sentences_and_overlap_starts_at_words():
    text = " ".join(f"Sentence number {i} is here." for i in range(60))
    body = text.encode()
    chunks = chunk_book(body, [Chapter("c", 0, len(body))], size=200, overlap=40)
    assert len(chunks) > 3
    for c in chunks[:-1]:
        assert len(c.text) <= 200 and c.text.rstrip().endswith(".")
    for c in chunks[1:]:
        assert c.text[0] != " " and not c.text[0].islower()  # starts at a word, not mid-word
    assert text.endswith(chunks[-1].text.strip())


def test_chunks_prefer_paragraph_breaks_and_know_their_chapter_index():
    para = "word " * 30
    body = (para.strip() + "\n\n" + para.strip()).encode()
    mid = len(body) // 2
    chunks = chunk_book(body, [Chapter("a", 0, mid), Chapter("b", mid, len(body))], size=200, overlap=0)
    assert [c.chapter_index for c in chunks] == [0, 1]


# ---------- converters ----------
def test_text_converter_uses_markdown_headings(tmp_path):
    f = tmp_path / "n.md"
    f.write_text("intro\n\n# My Book\n\ntext\n\n## Part 2\n\nmore\n")
    book = convert_text(f)
    assert book.title == "My Book"
    assert [c.title for c in book.chapters] == ["Front matter", "My Book", "Part 2"]


def test_registry_is_config_driven(config, tmp_path):
    assert supported_suffixes(config) == {".epub", ".txt", ".md"}
    on = type(config)(data_dir=config.data_dir, addons={"pdf": {"enabled": True}})
    assert ".pdf" in supported_suffixes(on)
    with pytest.raises(ConversionError):
        convert(tmp_path / "x.xyz", config)


# ---------- keyword + hybrid search ----------
@pytest.fixture
def full_store(config):
    return VectorStore(config.chroma_dir, config.keyword_db)


def _import_two(tmp_path, config, embeddings, store):
    a = make_epub(tmp_path / "a.epub", title="Alpha Tale", author="A Writer")
    b = make_epub(tmp_path / "b.epub", title="Beta Tale", author="B Writer", single_file=True)
    return (import_book(a, config, embeddings, store).slug,
            import_book(b, config, embeddings, store).slug)


def test_keyword_search_finds_exact_words_ignoring_diacritics(tmp_path, config, embeddings, full_store):
    _, beta = _import_two(tmp_path, config, embeddings, full_store)
    hits = search(embeddings, full_store, "umlauts", mode="keyword")
    assert hits and hits[0]["slug"] == beta
    assert search(embeddings, full_store, "ÜMLAUTS", mode="keyword")
    assert search(embeddings, full_store, "zzzz", mode="keyword") == []
    assert search(embeddings, full_store, "!!!", mode="keyword") == []


def test_hybrid_combines_both_and_reports_sources(tmp_path, config, embeddings, full_store):
    alpha, beta = _import_two(tmp_path, config, embeddings, full_store)
    hits = search(embeddings, full_store, "umlauts", top_k=3, mode="hybrid")
    assert hits[0]["slug"] == beta and "keyword" in hits[0]["sources"]
    assert all("chapter_index" in h for h in hits)
    assert search(embeddings, full_store, "x", slug=alpha, mode="hybrid")[0]["slug"] == alpha
    with pytest.raises(ValueError):
        search(embeddings, full_store, "x", mode="nope")


def test_hybrid_without_keyword_index_degrades_to_semantic(tmp_path, config, embeddings):
    store = VectorStore(config.chroma_dir)
    import_book(make_epub(tmp_path / "a.epub"), config, embeddings, store)
    assert search(embeddings, store, "chapter", mode="hybrid")


def test_removing_a_book_clears_all_indexes(tmp_path, config, embeddings, full_store):
    alpha, beta = _import_two(tmp_path, config, embeddings, full_store)
    assert admin.remove_book(config, full_store, beta)
    assert not admin.remove_book(config, full_store, beta)
    assert search(embeddings, full_store, "umlauts", mode="keyword") == []
    assert [e.slug for e in read_index(config.library_dir / "index.json")] == [alpha]
    assert not (config.library_dir / beta).exists()


# ---------- reading ----------
def test_get_chapter_windows_and_book_info(tmp_path, config, embeddings, full_store):
    f = tmp_path / "long.md"
    f.write_text("# Long\n\n" + "abcdefghij" * 100)
    slug = import_book(f, config, embeddings, full_store).slug

    whole = get_chapter(config, slug, "0", max_chars=0)
    first = get_chapter(config, slug, "0", max_chars=100)
    assert first.startswith(whole[:100]) and "offset=100" in first
    rest = get_chapter(config, slug, "0", offset=100, max_chars=0)
    assert whole[:100] + rest == whole
    assert "more characters" not in get_chapter(config, slug, "0")  # fits the default window

    info = get_book_info(config, slug)
    assert info["chapters"] == 1 and info["title"] == "Long" and "content_hash" not in info
    assert "not found" in get_book_info(config, "nope")


# ---------- embedding stamp + reindex ----------
def test_model_change_is_caught_and_reindex_fixes_it(tmp_path, config, embeddings, full_store):
    alpha, _ = _import_two(tmp_path, config, embeddings, full_store)
    assert stamp.read_stamp(config)["model"] == "bge-m3"

    other = type(config)(data_dir=config.data_dir, embedding_model="other-model",
                         chunk_size=500, chunk_overlap=50)
    assert "bge-m3" in stamp.problem(other)
    with pytest.raises(stamp.EmbeddingMismatch, match="reindex"):
        import_book(make_epub(tmp_path / "c.epub", title="C", author="C"), other, embeddings, full_store)

    total = reindex(other, embeddings)
    assert total > 0 and stamp.problem(other) is None
    fresh = VectorStore(other.chroma_dir, other.keyword_db)
    assert fresh.count() == total
    assert search(embeddings, fresh, "umlauts", mode="keyword")
    assert list(other.data_dir.glob("chroma.old-*")) and list(other.data_dir.glob("keyword.db.old-*"))


def test_dimension_mismatch_is_caught(tmp_path, config, embeddings, full_store):
    _import_two(tmp_path, config, embeddings, full_store)

    class FiveDims:
        def embed(self, texts):
            return [[1.0] * 5 for _ in texts]

    assert "5-dimensional" in stamp.problem(config, 5)
    with pytest.raises(stamp.EmbeddingMismatch):
        import_book(make_epub(tmp_path / "c.epub", title="C", author="C"), config, FiveDims(), full_store)


# ---------- doctor + cli ----------
def test_doctor_reports_failures_and_successes(tmp_path, config, embeddings, full_store):
    rows = {name: ok for name, ok, _ in admin.doctor(config, embeddings, full_store)}
    assert all(rows.values())

    class Down:
        def embed(self, texts):
            raise ConnectionRefusedError("down")

    rows = {name: ok for name, ok, _ in admin.doctor(config, Down(), full_store)}
    assert rows["embedding endpoint"] is False


def test_cli_list_remove_reindex_doctor(tmp_path, alice_epub, embeddings, monkeypatch, capsys):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(f"data_dir: {tmp_path / 'data'}\n")
    monkeypatch.setattr(cli, "EmbeddingsClient", lambda *a: embeddings)
    base = ["--config", str(cfg)]
    assert cli.main(base + ["import", str(alice_epub)]) == 0
    assert cli.main(base + ["list"]) == 0
    slug = capsys.readouterr().out.strip().splitlines()[-1].split("\t")[0]
    assert cli.main(base + ["doctor"]) == 0
    assert cli.main(base + ["reindex"]) == 0
    assert cli.main(base + ["remove", slug]) == 0
    assert cli.main(base + ["remove", slug]) == 1


def test_cli_import_reports_unsupported_and_bad_files(tmp_path, embeddings, monkeypatch, capsys):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(f"data_dir: {tmp_path / 'data'}\n")
    monkeypatch.setattr(cli, "EmbeddingsClient", lambda *a: embeddings)
    bad = tmp_path / "x.xyz"
    bad.write_text("hi")
    assert cli.main(["--config", str(cfg), "import", str(bad)]) == 1
    assert "unsupported" in capsys.readouterr().err
