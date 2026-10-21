"""Add-on: import text PDFs (needs `pip install "book-archivar[pdf]"`).

Chapters come from the PDF's bookmarks (outline). Without bookmarks, lines like
"Chapter 3" / "Kapitel 3" are used, and failing that blocks of pages. Scanned
PDFs contain no text; run OCR (e.g. ocrmypdf) first.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from book_archivar.chapters import chapters_from_boundaries
from book_archivar.converters import ConversionError, ConvertedBook

PAGES_PER_BLOCK = 20
_HEADING = re.compile(
    r"^(?:chapter|kapitel|chapitre|capítulo|capitolo|part|teil)\s+[\dIVXLC]+\b.{0,60}$",
    re.IGNORECASE | re.MULTILINE,
)
_SENTENCE_END = (".", "!", "?", "…", '"', "”", "»", "'", ")")


def _reflow(text: str) -> str:
    """Rebuild paragraphs from PDF line breaks: join wrapped lines, undo
    hyphenation, keep a break after a short line that ends a sentence."""
    lines = [l.strip() for l in text.splitlines()]
    longest = max((len(l) for l in lines), default=0)
    paragraphs: list[str] = []
    current = ""
    previous = ""
    for line in lines:
        if not line:
            if current:
                paragraphs.append(current)
            current = previous = ""
            continue
        if _HEADING.fullmatch(line):  # a heading always stands alone
            if current:
                paragraphs.append(current)
            paragraphs.append(line)
            current = previous = ""
            continue
        if not current:
            current = line
        elif current.endswith("-") and line[:1].islower():
            current = current[:-1] + line
        elif (previous.endswith(_SENTENCE_END) and len(previous) < 0.7 * longest
              and line[:1].isupper()):
            paragraphs.append(current)
            current = line
        else:
            current += " " + line
        previous = line
    if current:
        paragraphs.append(current)
    return "\n\n".join(paragraphs)


def _outline_pages(reader) -> list[tuple[int, str]]:
    """(page index, title) of every bookmark, in document order."""
    found: list[tuple[int, str]] = []

    def walk(items) -> None:
        for item in items:
            if isinstance(item, list):
                walk(item)
                continue
            try:
                found.append((reader.get_destination_page_number(item), str(item.title).strip()))
            except Exception:  # broken destination: skip that bookmark
                continue

    try:
        walk(reader.outline)
    except Exception:
        return []
    return [(p, t) for p, t in found if t and p is not None and p >= 0]


def _poppler_pages(path: Path, expected: int) -> list[str] | None:
    """Page texts via poppler's pdftotext when installed: about 8x faster than
    pypdf on large books. None if unavailable or inconsistent."""
    exe = shutil.which("pdftotext")
    if exe is None:
        return None
    try:
        result = subprocess.run([exe, "-enc", "UTF-8", str(path), "-"],
                                capture_output=True, timeout=900)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    pages = result.stdout.decode("utf-8", errors="replace").split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    return pages if len(pages) == expected else None


def convert_pdf(path: Path) -> ConvertedBook:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ConversionError(
            'PDF support needs the extra: pip install "book-archivar[pdf]"'
        ) from exc

    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            raise ConversionError(f"{path.name} is encrypted")
        raw_pages = _poppler_pages(path, len(reader.pages)) or [
            page.extract_text() or "" for page in reader.pages
        ]
        page_texts = [_reflow(text) for text in raw_pages]
        meta = reader.metadata
    except ConversionError:
        raise
    except Exception as exc:
        raise ConversionError(f"cannot read {path.name}: {exc}") from exc

    if not any(t.strip() for t in page_texts):
        raise ConversionError(f"{path.name} has no extractable text (scanned? run OCR first)")

    page_start: list[int] = []
    pieces: list[str] = []
    offset = 0
    for text in page_texts:
        page_start.append(offset)
        piece = text + "\n\n" if text else ""
        pieces.append(piece)
        offset += len(piece)
    body = "".join(pieces)

    boundaries: dict[int, str] = {}
    for page, title in _outline_pages(reader):
        boundaries.setdefault(page_start[min(page, len(page_start) - 1)], title)
    if len(boundaries) < 2:
        boundaries = {m.start(): m.group(0).strip() for m in _HEADING.finditer(body)}
    if len(boundaries) < 2:
        boundaries = {
            page_start[i]: f"Pages {i + 1}-{min(i + PAGES_PER_BLOCK, len(page_texts))}"
            for i in range(0, len(page_texts), PAGES_PER_BLOCK)
            if body[page_start[i]:].strip()
        }

    return ConvertedBook(
        title=((meta.title if meta else None) or path.stem).strip(),
        author=((meta.author if meta else None) or "Unknown").strip(),
        language="und",
        markdown=body,
        chapters=chapters_from_boundaries(body, sorted(boundaries.items())),
    )
