from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from book_archivar.chapters import read_chapters
from book_archivar.config import Config
from book_archivar.library import read_index
from book_archivar.vectorstore import VectorStore


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


def get_chapter(config: Config, book_slug: str, chapter_title_or_index: str) -> str:
    """Exact text of one chapter. A title match wins over an index, since books
    can have chapters literally titled "1", "2", ..."""
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
    return body[match.start_byte : match.end_byte].decode("utf-8", errors="ignore")


def build_server(config: Config, embeddings_client, vector_store: VectorStore) -> MCPServer:
    server: MCPServer = MCPServer(name="book-archivar")

    @server.tool(name="list_books")
    def _list_books() -> list[dict]:
        """List all archived books (slug, title, author, language)."""
        return list_books(config)

    @server.tool(name="search_books")
    def _search_books(query: str, book_slug: str | None = None, top_k: int = 5) -> list[dict]:
        """Semantic search over archived books, optionally scoped to one book_slug."""
        embedding = embeddings_client.embed([query])[0]
        return vector_store.query(embedding, top_k=top_k, slug=book_slug)

    @server.tool(name="list_chapters")
    def _list_chapters(book_slug: str) -> list[dict] | str:
        """List a book's chapters as {index, title}, for navigating with get_chapter."""
        return list_chapters(config, book_slug)

    @server.tool(name="get_chapter")
    def _get_chapter(book_slug: str, chapter_title_or_index: str) -> str:
        """Return the exact text of one chapter.

        chapter_title_or_index is a chapter title, or a numeric string
        ("0", "1", ...) selecting the chapter by its 0-based position.
        """
        return get_chapter(config, book_slug, chapter_title_or_index)

    return server
