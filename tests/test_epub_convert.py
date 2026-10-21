import pytest

from book_archivar.converters import ConversionError
from book_archivar.epub_convert import convert_epub
from tests.helpers import make_epub


def _text(book, i):
    c = book.chapters[i]
    return book.markdown.encode()[c.start_byte : c.end_byte].decode()


def test_metadata_and_chapters_from_toc(tmp_path):
    book = convert_epub(make_epub(tmp_path / "a.epub"))
    assert (book.title, book.author, book.language) == ("Test Book", "Doe, Jane", "en")
    titles = [c.title for c in book.chapters]
    assert titles[-2:] == ["One", "Two"]
    assert "Body of chapter One" in _text(book, titles.index("One"))
    assert "Body of chapter Two" not in _text(book, titles.index("One"))
    assert "- item" in book.markdown


def test_chapters_are_contiguous_and_cover_everything(tmp_path):
    book = convert_epub(make_epub(tmp_path / "a.epub"))
    total = len(book.markdown.encode())
    assert book.chapters[0].start_byte == 0
    assert book.chapters[-1].end_byte == total
    for a, b in zip(book.chapters, book.chapters[1:]):
        assert a.end_byte == b.start_byte


def test_toc_anchors_split_a_single_file(tmp_path):
    book = convert_epub(make_epub(tmp_path / "a.epub", single_file=True))
    titles = [c.title for c in book.chapters]
    assert titles[-2:] == ["First", "Second"]
    first = _text(book, titles.index("First"))
    assert "Alpha *text* with ümlauts." in first
    assert "Beta" not in first
    assert "Beta" in _text(book, titles.index("Second"))


def test_without_toc_falls_back_to_headings(tmp_path):
    book = convert_epub(make_epub(tmp_path / "a.epub", with_toc=False))
    assert [c.title for c in book.chapters if c.title in ("One", "Two")] == ["One", "Two"]


def test_alice_fixture_has_real_chapters(alice_epub):
    book = convert_epub(alice_epub)
    assert book.title == "Alice's Adventures in Wonderland"
    assert len(book.chapters) >= 10
    assert all(c.end_byte > c.start_byte for c in book.chapters)


def test_unreadable_file_raises(tmp_path):
    bad = tmp_path / "bad.epub"
    bad.write_text("not a zip")
    with pytest.raises(ConversionError):
        convert_epub(bad)


def test_degenerate_one_entry_toc_falls_back_to_documents(tmp_path):
    from ebooklib import epub

    path = make_epub(tmp_path / "a.epub")
    book = epub.read_epub(str(path))
    book.toc = [epub.Link("ch1.xhtml", "Start", "start")]
    epub.write_epub(str(path), book)

    titles = [c.title for c in convert_epub(path).chapters]
    assert "One" in titles and "Two" in titles
    assert "Start" not in titles
