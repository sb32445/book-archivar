"""EPUB -> Markdown plus chapter byte ranges, using only EbookLib and the stdlib.

Chapters come from the EPUB's table of contents (including anchors inside a
file, so single-file books still split correctly). Without a usable TOC, each
spine document becomes a chapter named after its first heading.
"""
from __future__ import annotations

import posixpath
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

import warnings

from ebooklib import ITEM_DOCUMENT, epub

from book_archivar.chapters import chapters_from_boundaries
from book_archivar.converters import ConversionError, ConvertedBook

_SKIP = {"script", "style", "head", "title"}
_BLOCK = {"p", "div", "li", "blockquote", "tr", "section", "article", "pre", "ul", "ol", "table"}
_HEADING = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_WS = re.compile(r"\s+")


class _HtmlToMarkdown(HTMLParser):
    """Minimal XHTML -> Markdown. Records the text offset of every id attribute
    and the text of the first heading."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.length = 0
        self.anchors: dict[str, int] = {}
        self.first_heading = ""
        self._newlines = 2  # start-of-document counts as a paragraph break
        self._skip_depth = 0
        self._heading_level = 0
        self._heading_text: list[str] = []

    def _emit(self, text: str) -> None:
        self.parts.append(text)
        self.length += len(text)
        if text.strip("\n"):
            self._newlines = 0
        else:
            self._newlines += len(text)

    def _break(self, n: int) -> None:
        if self._newlines < n:
            self._emit("\n" * (n - self._newlines))

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        attr = dict(attrs)
        if tag in _HEADING or tag in _BLOCK or tag == "br":
            if tag == "br":
                self._break(1)
            else:
                self._break(2 if tag not in {"li", "tr"} else 1)
        if attr.get("id"):
            self.anchors.setdefault(attr["id"], self.length)
        if tag in _HEADING:
            self._heading_level = _HEADING[tag]
            self._heading_text = []
            self._emit("#" * self._heading_level + " ")
        elif tag == "li":
            self._emit("- ")
        elif tag in {"em", "i"}:
            self._emit("*")
        elif tag in {"strong", "b"}:
            self._emit("**")

    def handle_endtag(self, tag):
        if tag in _SKIP:
            self._skip_depth = max(self._skip_depth - 1, 0)
            return
        if self._skip_depth:
            return
        if tag in _HEADING:
            if not self.first_heading:
                self.first_heading = _WS.sub(" ", "".join(self._heading_text)).strip()
            self._heading_level = 0
            self._break(2)
        elif tag in _BLOCK:
            self._break(2 if tag not in {"li", "tr"} else 1)
        elif tag in {"em", "i"}:
            self._emit("*")
        elif tag in {"strong", "b"}:
            self._emit("**")

    def handle_data(self, data):
        if self._skip_depth:
            return
        text = _WS.sub(" ", data)
        if self._newlines:
            text = text.lstrip()
        if not text:
            return
        if self._heading_level:
            self._heading_text.append(text)
        self._emit(text)


def _flatten_toc(toc) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if not isinstance(toc, (list, tuple)):  # EbookLib returns a bare Link for 1-entry TOCs
        toc = [toc]
    for node in toc:
        if isinstance(node, tuple):
            section, children = node
            out.extend(_flatten_toc([section]))
            out.extend(_flatten_toc(children))
        elif getattr(node, "href", None) and node.title:  # untitled entries are not chapters
            out.append((str(node.title).strip(), node.href))
    return out


def _first(book: epub.EpubBook, key: str, default: str) -> str:
    values = book.get_metadata("DC", key)
    return values[0][0] if values else default


def convert_epub(path: Path) -> ConvertedBook:
    try:
        with warnings.catch_warnings():  # EbookLib is noisy about its own deprecations
            warnings.simplefilter("ignore")
            book = epub.read_epub(str(path))
    except Exception as exc:  # EbookLib raises a zoo of exception types
        raise ConversionError(f"cannot read {path.name}: {exc}") from exc

    docs: list[tuple[str, _HtmlToMarkdown]] = []
    for idref, _linear in book.spine:
        item = book.get_item_with_id(idref)
        if item is None or item.get_type() != ITEM_DOCUMENT:
            continue
        parser = _HtmlToMarkdown()
        parser.feed(item.get_content().decode("utf-8", errors="replace"))
        docs.append((posixpath.normpath(item.get_name()), parser))
    if not docs:
        raise ConversionError(f"{path.name} has no readable content")

    # Concatenate the spine documents; remember where each starts and where
    # every anchor lands in the combined text.
    pieces: list[str] = []
    file_start: dict[str, int] = {}
    anchors: dict[tuple[str, str], int] = {}
    offset = 0
    for name, parser in docs:
        text = "".join(parser.parts)
        file_start[name] = offset
        for anchor, pos in parser.anchors.items():
            anchors[(name, anchor)] = offset + pos
        pieces.append(text)
        offset += len(text)
    body = "".join(pieces)

    title = _first(book, "title", path.stem)
    boundaries = _toc_boundaries(book, file_start, anchors)
    text_docs = [d for d in docs if "".join(d[1].parts).strip()]
    # Some EPUBs ship a one-entry TOC ("Start") for a book split into many
    # files; that says nothing about structure, so use the documents instead.
    if len(boundaries) < 3 and len(text_docs) > len(boundaries):
        boundaries = [
            (file_start[name], parser.first_heading or f"Section {i}")
            for i, (name, parser) in enumerate(text_docs, 1)
        ]

    return ConvertedBook(
        title=title,
        author=_first(book, "creator", "Unknown"),
        language=_first(book, "language", "und"),
        markdown=body,
        chapters=chapters_from_boundaries(body, boundaries),
    )


def _toc_boundaries(book, file_start, anchors) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for title, href in _flatten_toc(book.toc):
        target, _, fragment = unquote(href).partition("#")
        name = posixpath.normpath(target)
        if name not in file_start:
            continue
        pos = anchors.get((name, fragment), file_start[name]) if fragment else file_start[name]
        found.append((pos, title or f"Section {len(found) + 1}"))
    found.sort(key=lambda b: b[0])  # stable: a parent entry beats a child at the same offset
    deduped: list[tuple[int, str]] = []
    for pos, title in found:
        if not deduped or deduped[-1][0] != pos:
            deduped.append((pos, title))
    return deduped
