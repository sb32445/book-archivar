"""Add-on: import MOBI, AZW3, DOCX, FB2 ... through Calibre's `ebook-convert`.

Calibre stays an optional external tool: the file is converted to a temporary
EPUB, which then goes through the normal EPUB importer. Configure the
suffixes and, if needed, the binary path under `addons.calibre`.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from book_archivar.converters import Converter, ConversionError, ConvertedBook
from book_archivar.epub_convert import convert_epub

TIMEOUT_SECONDS = 600


def make_converter(options: dict) -> Converter:
    binary = options.get("binary", "ebook-convert")

    def convert(path: Path) -> ConvertedBook:
        exe = shutil.which(str(Path(binary).expanduser()))
        if exe is None:
            raise ConversionError(
                f"'{binary}' not found: install Calibre or set addons.calibre.binary"
            )
        with tempfile.TemporaryDirectory(prefix="book-archivar-") as tmp:
            out = Path(tmp) / "converted.epub"
            try:
                result = subprocess.run(
                    [exe, str(path), str(out)],
                    capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired as exc:
                raise ConversionError(f"ebook-convert timed out on {path.name}") from exc
            if result.returncode != 0 or not out.exists():
                raise ConversionError(
                    f"ebook-convert failed on {path.name}: {result.stderr.strip()[-300:]}"
                )
            book = convert_epub(out)
        if book.title == "converted":  # no title in the source: use the file name
            book = ConvertedBook(path.stem, book.author, book.language, book.markdown, book.chapters)
        return book

    return convert
