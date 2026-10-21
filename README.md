# book-archivar

Give an MCP-capable AI agent (Claude Desktop, Claude Code, your own agent) access to **your own EPUB library**, fully local:

- `list_books` – what is in the archive
- `search_books` – semantic search over all books (or one)
- `list_chapters` – a book's table of contents
- `get_chapter` – the exact text of one chapter, by title or index

Unlike plain chunk-search tools, the agent can navigate by chapter and read a whole chapter verbatim.

This is the **basic** edition: pure Python, no Rust, no daemon. Anything beyond that (inbox watcher, fuzzy duplicate review, ...) is meant to live in add-ons.

## Requirements

- Python 3.12+
- An OpenAI-compatible embeddings endpoint. The default is [Ollama](https://ollama.com): `ollama pull bge-m3`

## Install

    git clone <this repo> && cd book-archivar
    python3 -m venv venv
    ./venv/bin/pip install -e .

## Use

    # 1. import books (files or folders; originals are never touched or deleted)
    ./venv/bin/book-archivar import ~/Books

    # 2. run the MCP server (stdio)
    ./venv/bin/book-archivar serve

Claude Desktop (`claude_desktop_config.json`) / Claude Code (`claude mcp add`):

    {
      "mcpServers": {
        "books": { "command": "/path/to/venv/bin/book-archivar", "args": ["serve"] }
      }
    }

For a network service use `serve --transport streamable-http --host 127.0.0.1 --port 8000`.

## Add-on: inbox watcher

Drop EPUBs into a folder and they are imported automatically:

    ./venv/bin/book-archivar watch ~/book-inbox            # watcher only
    ./venv/bin/book-archivar serve --inbox ~/book-inbox    # MCP server + watcher

Or switch it on in `config.yaml` (`addons.inbox.enabled: true`, `path`, `interval`), after which plain `book-archivar serve` also watches the folder. Add-ons are off by default; every add-on has its own section under `addons:` in `config.example.yaml`.

Files are never deleted; they move to `processed/`, `duplicates/` (already in the library) or `failed/` (the file itself is broken). If the embedding endpoint is down, books simply wait in the inbox. `deploy/book-archivar.service` is a systemd user-service example.

## Configuration

Everything has a default; see `config.example.yaml`. Pass `--config FILE`, set `BOOK_ARCHIVAR_CONFIG`, or place a `config.yaml` in the working directory. Data lives in `~/.local/share/book-archivar` (`library/<slug>/{book.md,chapters.json,metadata.json}` plus `chroma/`).

**Changing the embedding model requires re-importing** (delete the data dir): vectors from different models are not comparable.

## How it works

EPUB → Markdown (EbookLib + a small HTML converter) → chapter byte ranges from the EPUB table of contents (anchors inside a file are honoured; without a TOC each document becomes a chapter) → fixed-size overlapping chunks per chapter → embeddings → Chroma. Importing the same file twice is detected by SHA-256.

## Limitations

- EPUB only (no PDF/MOBI).
- The Markdown conversion is deliberately simple: tables, footnotes and images are reduced to text.
- Chapter quality depends on the EPUB's TOC.
- Only use it with books you are allowed to use; do not publish the generated library.

## Tests

    ./venv/bin/pip install -e ".[dev]" && ./venv/bin/pytest

Dual-licensed under [MIT](LICENSE-MIT) or [Apache-2.0](LICENSE-APACHE), at your option.
