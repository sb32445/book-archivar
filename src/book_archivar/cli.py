from __future__ import annotations

import argparse
import logging
import sys
import threading
from pathlib import Path

from book_archivar.addons import review
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


def review_dir(config: Config) -> Path | None:
    """Where the duplicates add-on parks suspects; None while the add-on is off."""
    options = config.addon_options("duplicates")
    if options is None:
        return None
    return Path(options.get("review_dir", config.data_dir / "review")).expanduser()


def _import_fn(config: Config, embeddings_client, vector_store):
    return lambda p: import_epub(
        p, config, embeddings_client, vector_store, review_dir=review_dir(config)
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
            outcome = _import_fn(config, embeddings_client, vector_store)(epub)
        except (ConversionError, OSError) as exc:
            print(f"FAILED   {epub}: {exc}", file=sys.stderr)
            failures += 1
        else:
            print(f"{outcome.status.upper():8} {epub.name} -> {outcome.slug}")
    return 1 if failures else 0


def _watcher(config: Config, inbox: Path, embeddings_client, vector_store) -> InboxWatcher:
    return InboxWatcher(inbox, _import_fn(config, embeddings_client, vector_store))


def cmd_watch(config: Config, inbox: Path, interval: float) -> int:
    embeddings_client, vector_store = _clients(config)
    watcher = _watcher(config, inbox, embeddings_client, vector_store)
    try:
        watcher.run_forever(interval)
    except KeyboardInterrupt:
        pass
    return 0


def cmd_review(config: Config, action: str, entry: str | None) -> int:
    directory = review_dir(config)
    if directory is None:
        print("the duplicates add-on is not enabled (addons.duplicates.enabled)", file=sys.stderr)
        return 1
    if action == "list":
        for item in review.list_entries(directory):
            print(f"{item['entry']}  (matches {item['matched_slug']})")
        return 0
    if entry is None:
        print(f"{action} needs an entry name (see `review list`)", file=sys.stderr)
        return 2
    embeddings_client, vector_store = _clients(config)
    review.resolve(directory / entry, action, config, embeddings_client, vector_store)
    print(f"{action}: {entry}")
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


def _inbox_settings(config: Config, args) -> tuple[Path | None, float]:
    """Inbox folder and poll interval: command line first, then the config's
    `addons.inbox` section (which only applies to `serve` when enabled)."""
    options = config.addon_options("inbox") if args.command == "serve" else (
        config.addons.get("inbox") or {}
    )
    inbox = args.inbox
    if inbox is None and options and options.get("path"):
        inbox = Path(options["path"]).expanduser()
    interval = args.interval or float((options or {}).get("interval", 60))
    return inbox, interval


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="book-archivar")
    parser.add_argument("--config", type=Path, help="path to config.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    p_import = sub.add_parser("import", help="import EPUB files (or folders of them)")
    p_import.add_argument("paths", nargs="+", type=Path)

    p_watch = sub.add_parser("watch", help="import EPUBs dropped into a folder (add-on)")
    p_watch.add_argument("inbox", type=Path, nargs="?", help="default: addons.inbox.path")
    p_watch.add_argument("--interval", type=float, help="poll seconds (default 60)")

    p_review = sub.add_parser("review", help="resolve suspected duplicates (add-on)")
    p_review.add_argument("action", choices=["list", *review.ACTIONS])
    p_review.add_argument("entry", nargs="?", help="folder name from `review list`")

    p_serve = sub.add_parser("serve", help="run the MCP server")
    p_serve.add_argument("--inbox", type=Path, help="also watch this folder (add-on)")
    p_serve.add_argument("--interval", type=float, help="inbox poll seconds (default 60)")
    p_serve.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    config = load_config(args.config)

    if args.command == "import":
        return cmd_import(config, args.paths)
    if args.command == "review":
        return cmd_review(config, args.action, args.entry)
    inbox, interval = _inbox_settings(config, args)
    if args.command == "watch":
        if inbox is None:
            parser.error("watch needs a folder argument or addons.inbox.path in the config")
        return cmd_watch(config, inbox, interval)
    return cmd_serve(config, args.transport, args.host, args.port, inbox, interval)


if __name__ == "__main__":
    sys.exit(main())
