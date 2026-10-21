import shutil
import stat

import pytest

from book_archivar.addons.calibre import make_converter
from book_archivar.addons.inbox import InboxWatcher
from book_archivar.addons.pdf import _reflow, convert_pdf
from book_archivar.config import Config
from book_archivar.converters import ConversionError, convert
from book_archivar.importer import ImportOutcome, import_book
from book_archivar.vectorstore import VectorStore
from tests.helpers import make_epub, make_pdf


def _text(book, i):
    c = book.chapters[i]
    return book.markdown.encode()[c.start_byte : c.end_byte].decode()


# ---------- PDF ----------
def test_pdf_chapters_from_bookmarks(tmp_path):
    pdf = make_pdf(
        tmp_path / "b.pdf",
        [["Title page"], ["First chapter text", "continues here."], ["Second chapter text."]],
        outline=[("One", 1), ("Two", 2)], title="PDF Book",
    )
    book = convert_pdf(pdf)
    assert (book.title, book.author) == ("PDF Book", "Pat Author")
    assert [c.title for c in book.chapters] == ["Front matter", "One", "Two"]
    assert "First chapter text continues here." in _text(book, 1)
    assert "Second chapter" in _text(book, 2) and "First" not in _text(book, 2)


def test_pdf_without_bookmarks_uses_chapter_lines_then_page_blocks(tmp_path):
    pdf = make_pdf(tmp_path / "c.pdf", [["Chapter 1", "alpha text"], ["Chapter 2", "beta text"]])
    assert [c.title for c in convert_pdf(pdf).chapters] == ["Chapter 1", "Chapter 2"]

    plain = make_pdf(tmp_path / "p.pdf", [[f"page {i} text"] for i in range(45)])
    titles = [c.title for c in convert_pdf(plain).chapters]
    assert titles == ["Pages 1-20", "Pages 21-40", "Pages 41-45"]


def test_pdf_without_text_or_broken_is_a_clear_error(tmp_path):
    empty = make_pdf(tmp_path / "e.pdf", [[], []])
    with pytest.raises(ConversionError, match="OCR"):
        convert_pdf(empty)
    bad = tmp_path / "bad.pdf"
    bad.write_text("nope")
    with pytest.raises(ConversionError):
        convert_pdf(bad)


def test_reflow_joins_lines_and_dehyphenates():
    text = "This is a long line that wraps and con-\ntinues here and ends.\nShort end.\nNext paragraph starts."
    out = _reflow(text)
    assert "continues here" in out and "con-" not in out
    assert out.split("\n\n")[-1] == "Next paragraph starts."  # short sentence-ending lines break


def test_pdf_import_end_to_end_via_config(tmp_path, embeddings):
    cfg = Config(data_dir=tmp_path / "d", addons={"pdf": {"enabled": True}})
    pdf = make_pdf(tmp_path / "b.pdf", [["Hello PDF world."]], title="Tiny")
    outcome = import_book(pdf, cfg, embeddings, VectorStore(cfg.chroma_dir))
    assert outcome.status == "imported"
    off = Config(data_dir=tmp_path / "d2")
    with pytest.raises(ConversionError, match="unsupported"):
        convert(pdf, off)


# ---------- Calibre ----------
def test_calibre_wrapper_with_fake_binary(tmp_path):
    epub = make_epub(tmp_path / "src.epub", title="Via Fake", author="X")
    fake = tmp_path / "fake-convert"
    fake.write_text(f'#!/bin/sh\ncp "{epub}" "$2"\n')
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    book = make_converter({"binary": str(fake)})(tmp_path / "in.mobi")
    assert book.title == "Via Fake"


def test_calibre_errors_are_clear(tmp_path):
    with pytest.raises(ConversionError, match="not found"):
        make_converter({"binary": "definitely-not-installed"})(tmp_path / "in.mobi")
    failing = tmp_path / "fail"
    failing.write_text("#!/bin/sh\necho oops >&2\nexit 3\n")
    failing.chmod(failing.stat().st_mode | stat.S_IEXEC)
    with pytest.raises(ConversionError, match="oops"):
        make_converter({"binary": str(failing)})(tmp_path / "in.mobi")


@pytest.mark.skipif(shutil.which("ebook-convert") is None, reason="Calibre not installed")
def test_calibre_real_conversion_of_a_text_file(tmp_path):
    src = tmp_path / "story.txt"
    src.write_text("A Title\n\n" + "Some words in a paragraph. " * 20)
    book = make_converter({})(src)
    assert "Some words" in book.markdown


# ---------- inbox with several formats ----------
def test_inbox_picks_up_configured_suffixes(tmp_path):
    inbox = tmp_path / "in"
    inbox.mkdir()
    for name in ("a.epub", "b.pdf", "c.txt"):
        (inbox / name).write_bytes(b"x")
    seen = []
    w = InboxWatcher(inbox, lambda p: seen.append(p.name) or ImportOutcome("imported", "s"),
                     suffixes={".epub", ".pdf"})
    w.poll_once(); w.poll_once()
    assert sorted(seen) == ["a.epub", "b.pdf"]
