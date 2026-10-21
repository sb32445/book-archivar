from __future__ import annotations

import json
import logging

from mcp.server.mcpserver import MCPServer

from book_archivar.chapters import read_chapters
from book_archivar.config import Config
from book_archivar.library import read_index
from book_archivar.search import search
from book_archivar.vectorstore import VectorStore

logger = logging.getLogger(__name__)


def list_books(config: Config) -> list[dict]:
    return [
        {"slug": e.slug, "title": e.title, "author": e.author, "language": e.language}
        for e in read_index(config.library_dir / "index.json")
    ]


def list_chapters(config: Config, book_slug: str) -> list[dict] | str:
    chapters_json = config.library_dir / book_slug / "chapters.json"
    if not chapters_json.exists():
        return f"book '{book_slug}' not found"
    return [{"index": i, "title": c.title} for i, c in enumerate(read_chapters(chapters_json))]


DEFAULT_MAX_CHARS = 30_000


def get_chapter(
    config: Config,
    book_slug: str,
    chapter_title_or_index: str,
    offset: int = 0,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> str:
    """Text of one chapter, at most `max_chars` characters starting at `offset`.

    A title match wins over an index, since books can have chapters literally
    titled "1", "2", ... When the chapter is longer than the window, a final
    line says how to fetch the rest.
    """
    book_dir = config.library_dir / book_slug
    if not (book_dir / "book.md").exists() or not (book_dir / "chapters.json").exists():
        return f"book '{book_slug}' not found"

    chapters = read_chapters(book_dir / "chapters.json")
    match = next((c for c in chapters if c.title == chapter_title_or_index), None)
    if match is None:
        try:
            index = int(str(chapter_title_or_index).strip())
        except ValueError:
            index = -1
        if 0 <= index < len(chapters):
            match = chapters[index]
    if match is None:
        return f"chapter '{chapter_title_or_index}' not found in book '{book_slug}'"

    body = (book_dir / "book.md").read_bytes()
    text = body[match.start_byte : match.end_byte].decode("utf-8", errors="ignore")
    offset = max(offset, 0)
    if max_chars <= 0 or offset == 0 and len(text) <= max_chars:
        return text[offset:] if max_chars <= 0 else text
    window = text[offset : offset + max_chars]
    end = offset + len(window)
    if end < len(text):
        window += (f"\n\n[... {len(text) - end} more characters. "
                   f"Call again with offset={end} to continue.]")
    return window


def get_book_info(config: Config, book_slug: str) -> dict | str:
    book_dir = config.library_dir / book_slug
    if not (book_dir / "metadata.json").exists():
        return f"book '{book_slug}' not found"
    info = json.loads((book_dir / "metadata.json").read_text())
    chapters = read_chapters(book_dir / "chapters.json")
    info.pop("content_hash", None)
    info["slug"] = book_slug
    info["chapters"] = len(chapters)
    info["characters"] = len((book_dir / "book.md").read_text(encoding="utf-8", errors="ignore"))
    return info


def build_server(config: Config, embeddings_client, vector_store: VectorStore) -> MCPServer:
    server: MCPServer = MCPServer(name="book-archivar")

    @server.tool(name="list_books")
    def _list_books() -> list[dict]:
        """List all archived books (slug, title, author, language)."""
        result = list_books(config)
        logger.info("tool=list_books books=%d", len(result))
        return result

    @server.tool(name="search_books")
    def _search_books(
        query: str, book_slug: str | None = None, top_k: int = 5, mode: str = "hybrid"
    ) -> list[dict]:
        """Search the archive. mode: "hybrid" (default; meaning + exact words),
        "semantic" or "keyword". Optionally scoped to one book_slug. Each hit
        has chapter_index/chapter_title: pass them to get_chapter to read on."""
        results = search(embeddings_client, vector_store, query, book_slug, top_k, mode)
        # metadata only: never log the query or book text
        logger.info("tool=search_books book_slug=%s top_k=%d mode=%s results=%d",
                    book_slug, top_k, mode, len(results))
        return results

    @server.tool(name="list_chapters")
    def _list_chapters(book_slug: str) -> list[dict] | str:
        """List a book's chapters as {index, title}, for navigating with get_chapter."""
        result = list_chapters(config, book_slug)
        logger.info("tool=list_chapters book_slug=%s chapters=%s", book_slug,
                    len(result) if isinstance(result, list) else "error")
        return result

    @server.tool(name="get_chapter")
    def _get_chapter(
        book_slug: str,
        chapter_title_or_index: str,
        offset: int = 0,
        max_chars: int = DEFAULT_MAX_CHARS,
    ) -> str:
        """Return the text of one chapter.

        chapter_title_or_index is a chapter title, or a numeric string
        ("0", "1", ...) selecting the chapter by its 0-based position. Long
        chapters come in windows of max_chars characters; the end of the
        text says which offset to continue with. max_chars=0 means everything.
        """
        text = get_chapter(config, book_slug, chapter_title_or_index, offset, max_chars)
        logger.info("tool=get_chapter book_slug=%s chapter=%s offset=%d bytes=%d", book_slug,
                    chapter_title_or_index, offset, len(text.encode("utf-8")))
        return text

    @server.tool(name="get_book_info")
    def _get_book_info(book_slug: str) -> dict | str:
        """Title, author, language, number of chapters and size of one book."""
        return get_book_info(config, book_slug)

    return server
