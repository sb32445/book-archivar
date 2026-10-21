from __future__ import annotations

import argparse
import logging
import sys
import threading
from pathlib import Path

from book_archivar import admin
from book_archivar.addons import review
from book_archivar.addons.inbox import InboxWatcher
from book_archivar.addons.jsonlog import configure_logging
from book_archivar.config import Config, load_config
from book_archivar.converters import ConversionError, supported_suffixes
from book_archivar.embeddings import EmbeddingsClient
from book_archivar.importer import import_book
from book_archivar.library import read_index
from book_archivar.mcp_server import build_server
from book_archivar.reindex import reindex
from book_archivar.stamp import EmbeddingMismatch, problem
from book_archivar.vectorstore import VectorStore

logger = logging.getLogger(__name__)


def _clients(config: Config) -> tuple[EmbeddingsClient, VectorStore]:
    return (
        EmbeddingsClient(
            config.embedding_base_url, config.embedding_api_key, config.embedding_model
        ),
        VectorStore(config.chroma_dir, config.keyword_db),
    )


def review_dir(config: Config) -> Path | None:
    """Where the duplicates add-on parks suspects; None while the add-on is off."""
    options = config.addon_options("duplicates")
    if options is None:
        return None
    return Path(options.get("review_dir", config.data_dir / "review")).expanduser()


def _import_fn(config: Config, embeddings_client, vector_store):
    return lambda p: import_book(
        p, config, embeddings_client, vector_store, review_dir=review_dir(config)
    )


def _collect_books(paths: list[Path], suffixes: set[str]) -> list[Path]:
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            found.extend(sorted(f for f in path.rglob("*") if f.suffix.lower() in suffixes))
        else:
            found.append(path)
    return found


def cmd_import(config: Config, paths: list[Path]) -> int:
    embeddings_client, vector_store = _clients(config)
    import_fn = _import_fn(config, embeddings_client, vector_store)
    failures = 0
    for book in _collect_books(paths, supported_suffixes(config)):
        try:
            outcome = import_fn(book)
        except (ConversionError, EmbeddingMismatch, OSError) as exc:
            print(f"FAILED   {book}: {exc}", file=sys.stderr)
            failures += 1
        else:
            print(f"{outcome.status.upper():8} {book.name} -> {outcome.slug}")
    return 1 if failures else 0


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


def _watcher(config: Config, inbox: Path, embeddings_client, vector_store) -> InboxWatcher:
    return InboxWatcher(
        inbox,
        _import_fn(config, embeddings_client, vector_store),
        suffixes=supported_suffixes(config),
    )


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


def cmd_list(config: Config) -> int:
    for e in read_index(config.library_dir / "index.json"):
        print(f"{e.slug}\t{e.author}\t{e.title}")
    return 0


def cmd_remove(config: Config, slug: str) -> int:
    _, vector_store = _clients(config)
    if admin.remove_book(config, vector_store, slug):
        print(f"removed {slug}")
        return 0
    print(f"no such book: {slug} (see `book-archivar list`)", file=sys.stderr)
    return 1


def cmd_doctor(config: Config) -> int:
    embeddings_client, vector_store = _clients(config)
    rows = admin.doctor(config, embeddings_client, vector_store)
    for check, ok, detail in rows:
        print(f"[{'ok' if ok else 'FAIL'}] {check}: {detail}")
    return 0 if all(ok for _, ok, _ in rows) else 1


def cmd_reindex(config: Config) -> int:
    embeddings_client, _ = _clients(config)
    chunks = reindex(config, embeddings_client, progress=print)
    print(f"done: {chunks} chunks. The previous index was kept as *.old-<timestamp>; "
          "delete it when you are happy.")
    return 0


def cmd_serve(
    config: Config, transport: str, host: str, port: int,
    inbox: Path | None = None, interval: float = 60,
) -> int:
    embeddings_client, vector_store = _clients(config)
    if (message := problem(config)) is not None:
        logger.warning("%s. Searches will fail until you run `book-archivar reindex`.", message)
    if inbox is not None:
        watcher = _watcher(config, inbox, embeddings_client, vector_store)
        threading.Thread(
            target=watcher.run_forever, args=(interval,), daemon=True, name="inbox"
        ).start()
    server = build_server(config, embeddings_client, vector_store)
    if transport == "stdio":
        server.run("stdio")
    else:
        if host not in ("127.0.0.1", "localhost", "::1"):
            logger.warning(
                "serving on %s without authentication: anyone who can reach the port can "
                "read your whole library. Prefer 127.0.0.1 or put an authenticating proxy in front.",
                host,
            )
        server.run("streamable-http", host=host, port=port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="book-archivar")
    parser.add_argument("--config", type=Path, help="path to config.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    p_import = sub.add_parser("import", help="import books (files or folders)")
    p_import.add_argument("paths", nargs="+", type=Path)

    sub.add_parser("list", help="list the books in the library")

    p_remove = sub.add_parser("remove", help="remove a book from library and indexes")
    p_remove.add_argument("slug")

    sub.add_parser("doctor", help="check embedding endpoint, index and library")
    sub.add_parser("reindex", help="rebuild the search indexes from the library")

    p_watch = sub.add_parser("watch", help="import books dropped into a folder (add-on)")
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
    log_options = config.addon_options("logging")
    if log_options is not None:
        configure_logging(
            Path(log_options.get("dir", config.data_dir / "logs")).expanduser(),
            getattr(logging, str(log_options.get("level", "INFO")).upper(), logging.INFO),
        )

    if args.command == "import":
        return cmd_import(config, args.paths)
    if args.command == "list":
        return cmd_list(config)
    if args.command == "remove":
        return cmd_remove(config, args.slug)
    if args.command == "doctor":
        return cmd_doctor(config)
    if args.command == "reindex":
        return cmd_reindex(config)
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
