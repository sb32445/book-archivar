from __future__ import annotations

import argparse
import logging
import sys
import threading
from pathlib import Path

from book_archivar.addons.inbox import InboxWatcher
from book_archivar.config import Config, load_config
from book_archivar.embeddings import EmbeddingsClient
from book_archivar.epub_convert import ConversionError
from book_archivar.importer import import_epub
from book_archivar.mcp_server import build_server
from book_archivar.vectorstore import VectorStore


def _clients(config: Config) -> tuple[EmbeddingsClient, VectorStore]:
    return (
        EmbeddingsClient(
            config.embedding_base_url, config.embedding_api_key, config.embedding_model
        ),
        VectorStore(config.chroma_dir),
    )


def _collect_epubs(paths: list[Path]) -> list[Path]:
    found: list[Path] = []
    for path in paths:
        found.extend(sorted(path.rglob("*.epub")) if path.is_dir() else [path])
    return found


def cmd_import(config: Config, paths: list[Path]) -> int:
    embeddings_client, vector_store = _clients(config)
    failures = 0
    for epub in _collect_epubs(paths):
        try:
            outcome = import_epub(epub, config, embeddings_client, vector_store)
        except (ConversionError, OSError) as exc:
            print(f"FAILED   {epub}: {exc}", file=sys.stderr)
            failures += 1
        else:
            print(f"{outcome.status.upper():8} {epub.name} -> {outcome.slug}")
    return 1 if failures else 0


def _watcher(config: Config, inbox: Path, embeddings_client, vector_store) -> InboxWatcher:
    return InboxWatcher(
        inbox, lambda p: import_epub(p, config, embeddings_client, vector_store)
    )


def cmd_watch(config: Config, inbox: Path, interval: float) -> int:
    embeddings_client, vector_store = _clients(config)
    watcher = _watcher(config, inbox, embeddings_client, vector_store)
    try:
        watcher.run_forever(interval)
    except KeyboardInterrupt:
        pass
    return 0


def cmd_serve(
    config: Config, transport: str, host: str, port: int,
    inbox: Path | None = None, interval: float = 60,
) -> int:
    embeddings_client, vector_store = _clients(config)
    if inbox is not None:
        watcher = _watcher(config, inbox, embeddings_client, vector_store)
        threading.Thread(
            target=watcher.run_forever, args=(interval,), daemon=True, name="inbox"
        ).start()
    server = build_server(config, embeddings_client, vector_store)
    if transport == "stdio":
        server.run("stdio")
    else:
        server.run("streamable-http", host=host, port=port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="book-archivar")
    parser.add_argument("--config", type=Path, help="path to config.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    p_import = sub.add_parser("import", help="import EPUB files (or folders of them)")
    p_import.add_argument("paths", nargs="+", type=Path)

    p_watch = sub.add_parser("watch", help="import EPUBs dropped into a folder (add-on)")
    p_watch.add_argument("inbox", type=Path)
    p_watch.add_argument("--interval", type=float, default=60, help="poll seconds")

    p_serve = sub.add_parser("serve", help="run the MCP server")
    p_serve.add_argument("--inbox", type=Path, help="also watch this folder (add-on)")
    p_serve.add_argument("--interval", type=float, default=60, help="inbox poll seconds")
    p_serve.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    config = load_config(args.config)

    if args.command == "import":
        return cmd_import(config, args.paths)
    if args.command == "watch":
        return cmd_watch(config, args.inbox, args.interval)
    return cmd_serve(
        config, args.transport, args.host, args.port, args.inbox, args.interval
    )


if __name__ == "__main__":
    sys.exit(main())
