# book-archivar

Give an MCP-capable AI agent (Claude Desktop, Claude Code, your own agent) access to **your own book library**, fully local. The agent can search it by meaning *and* by exact words, look at a book's chapters, and read any chapter verbatim.

MCP tools:

| Tool | What it does |
|---|---|
| `list_books` | what is in the archive |
| `get_book_info` | title, author, language, chapter count, size |
| `search_books` | `hybrid` (default), `semantic` or `keyword` search, optionally within one book; hits carry `chapter_index` |
| `list_chapters` | a book's table of contents |
| `get_chapter` | text of one chapter by title or index; long chapters come in windows (`offset`, `max_chars`) |

Core: pure Python, EPUB, plain text and Markdown. Everything else is an opt-in add-on (see below).

## Requirements

- Python 3.12+
- An OpenAI-compatible embeddings endpoint. The default is [Ollama](https://ollama.com): `ollama pull bge-m3`

## Install

    git clone https://github.com/sb32445/book-archivar && cd book-archivar
    python3 -m venv venv
    ./venv/bin/pip install -e .            # add ".[pdf]" for PDF support

## Use

    ./venv/bin/book-archivar doctor                  # is the embedding endpoint reachable?
    ./venv/bin/book-archivar import ~/Books          # files or folders; originals are never touched
    ./venv/bin/book-archivar serve                   # MCP server on stdio

Other commands: `list`, `remove <slug>`, `reindex`, `watch`, `review` (the last two are add-ons).

Claude Desktop (`claude_desktop_config.json`) / Claude Code (`claude mcp add`):

    {
      "mcpServers": {
        "books": { "command": "/path/to/venv/bin/book-archivar", "args": ["serve"] }
      }
    }

For a network service use `serve --transport streamable-http --host 127.0.0.1 --port 8000`. There is **no authentication**: keep it on loopback or put an authenticating proxy in front.

## Using it with an agent

`example/SKILL.md` is a template skill that tells an agent when and how to use the five tools (searching, quoting, reading long chapters). Copy it into your agent's skills folder and adapt it.

## Configuration

Everything has a default; see `config.example.yaml`. Pass `--config FILE`, set `BOOK_ARCHIVAR_CONFIG`, or place a `config.yaml` in the working directory. Data lives in `~/.local/share/book-archivar`: `library/<slug>/{book.md,chapters.json,metadata.json}`, `chroma/` (vectors), `keyword.db` (full-text index).

## Changing the embedding model

Vectors from different models are not comparable. The index remembers which model built it; importing with another model fails with a clear message. Run

    ./venv/bin/book-archivar reindex

to rebuild both indexes from `library/` (no original files needed). The old index is kept as `chroma.old-<timestamp>` until you delete it. Stop `serve` first. The same command repairs a damaged index, and applies new `chunk_size` settings.

## How it works

Book → Markdown plus chapter byte ranges → overlapping chunks that end at paragraph/sentence boundaries → embeddings → Chroma, and the same chunks into an SQLite FTS5 index. Hybrid search fuses both rankings (reciprocal rank fusion): meaning finds paraphrases, keywords find names and quotes. EPUB chapters come from the table of contents, including anchors inside a file; without one, each document becomes a chapter. The same file (SHA-256) is never imported twice.

## Add-ons

All off by default; enable each under `addons:` in `config.yaml`.

**Inbox watcher** (`addons.inbox`) – drop books into a folder and they are imported: `book-archivar watch ~/inbox`, or with `serve` when enabled. Files are never deleted; they move to `processed/`, `duplicates/`, `review/` or `failed/`. If the embedding endpoint is down, books simply wait. `deploy/book-archivar.service` is a systemd example.

**Duplicate review** (`addons.duplicates`) – a book whose author and title match an existing one but whose file differs is parked in `review/` instead of imported. Decide with `book-archivar review list|keep-both|replace|discard <entry>`. `replace` imports first and removes the old copy only afterwards. Stop `serve` while resolving.

**JSON log file** (`addons.logging`) – rotating JSON-lines log of imports, review decisions and every tool call. Metadata only, never queries or book text.

**PDF** (`addons.pdf`, `pip install "book-archivar[pdf]"`) – chapters from the PDF's bookmarks; without them "Chapter N" lines, else blocks of 20 pages. Uses poppler's `pdftotext` if installed (about 10x faster), otherwise pypdf. Scanned PDFs have no text; run OCR (`ocrmypdf`) first.

**Calibre fallback** (`addons.calibre`) – MOBI, AZW3, FB2, DOCX, ODT, RTF via Calibre's `ebook-convert` (must be installed). The file is converted to a temporary EPUB and imported normally.

## Limitations

- The conversion is deliberately simple: tables, footnotes and images are reduced to text. PDF layouts with columns can read oddly.
- Chapter quality depends on the book's table of contents.
- Only use it with books you are allowed to use; do not publish the generated library.

## Tests

    ./venv/bin/pip install -e ".[dev]" && ./venv/bin/pytest

Dual-licensed under [MIT](LICENSE-MIT) or [Apache-2.0](LICENSE-APACHE), at your option.
