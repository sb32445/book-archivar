# Changelog

## Unreleased
- Hybrid search (meaning + exact words) via an SQLite FTS5 keyword index; `mode` parameter on `search_books`.
- Chunks now end at paragraph, sentence or word boundaries instead of mid-word.
- `get_chapter` reads long chapters in windows (`offset`, `max_chars`); new `get_book_info` tool; search hits carry `chapter_index`.
- The index remembers its embedding model/dimensions and refuses mismatching imports; `book-archivar reindex` rebuilds the indexes from `library/`.
- New commands: `list`, `remove`, `doctor`, `reindex`.
- Plain text and Markdown import. Add-ons: PDF (`pypdf`), Calibre fallback (MOBI, AZW3, DOCX, ...).
- Warning when serving HTTP on a non-loopback address (no authentication).

## 0.1.0
- Inbox watcher, duplicate review and JSON log file add-ons (all off by default).
- Basic edition: EPUB import, chapter-aware reading, semantic search over MCP.
