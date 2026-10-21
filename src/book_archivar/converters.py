"""Book formats: which file types can be imported and how they are converted.

Every converter turns one file into a ConvertedBook (Markdown text plus chapter
byte ranges). EPUB, plain text and Markdown are built in; PDF and the Calibre
fallback are add-ons that register themselves when enabled in the config.
"""
from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Callable

from book_archivar.chapters import Chapter, chapters_from_boundaries
from book_archivar.config import Config


class ConversionError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class ConvertedBook:
    title: str
    author: str
    language: str
    markdown: str
    chapters: list[Chapter]


Converter = Callable[[Path], ConvertedBook]

_MD_HEADING = re.compile(r"^(#{1,2})[ \t]+(.+?)[ \t]*#*[ \t]*$", re.MULTILINE)


def convert_text(path: Path) -> ConvertedBook:
    """Plain text / Markdown. Chapters are the `#` and `##` headings, if any."""
    try:
        body = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ConversionError(f"cannot read {path.name}: {exc}") from exc
    if not body.strip():
        raise ConversionError(f"{path.name} is empty")

    headings = [(m.start(), m.group(2).strip(), len(m.group(1))) for m in _MD_HEADING.finditer(body)]
    title = next((t for _, t, level in headings if level == 1), path.stem)
    return ConvertedBook(
        title=title,
        author="Unknown",
        language="und",
        markdown=body,
        chapters=chapters_from_boundaries(body, [(pos, t) for pos, t, _ in headings]),
    )


def registry(config: Config) -> dict[str, Converter]:
    """Suffix -> converter for everything this configuration can import."""
    from book_archivar.epub_convert import convert_epub

    converters: dict[str, Converter] = {
        ".epub": convert_epub,
        ".txt": convert_text,
        ".md": convert_text,
    }
    if config.addon_options("calibre") is not None:
        from book_archivar.addons.calibre import make_converter

        options = config.addon_options("calibre")
        for suffix in options.get("suffixes", [".mobi", ".azw3", ".fb2", ".docx", ".odt", ".rtf"]):
            converters[suffix.lower()] = make_converter(options)
    if config.addon_options("pdf") is not None:
        from book_archivar.addons.pdf import convert_pdf

        converters[".pdf"] = convert_pdf
    return converters


def supported_suffixes(config: Config) -> set[str]:
    return set(registry(config))


def convert(path: Path, config: Config) -> ConvertedBook:
    converter = registry(config).get(path.suffix.lower())
    if converter is None:
        raise ConversionError(
            f"unsupported file type '{path.suffix}' (supported: {sorted(supported_suffixes(config))})"
        )
    return converter(path)
