import asyncio
import json
import logging

import pytest

from book_archivar import cli
from book_archivar.addons.jsonlog import LOG_FILENAME, JsonLinesFormatter, configure_logging
from book_archivar.mcp_server import build_server
from book_archivar.vectorstore import VectorStore


@pytest.fixture
def clean_root_logger():
    root = logging.getLogger()
    before, level = list(root.handlers), root.level
    yield root
    for h in list(root.handlers):
        if h not in before:
            root.removeHandler(h)
            h.close()
    root.setLevel(level)


def test_writes_json_lines_with_extra_fields(tmp_path, clean_root_logger):
    configure_logging(tmp_path)
    configure_logging(tmp_path)  # idempotent
    logging.getLogger("t").info("hello %s", "x", extra={"book": "b"})
    try:
        raise ValueError("boom")
    except ValueError:
        logging.getLogger("t").exception("failed")
    for h in clean_root_logger.handlers:
        h.flush()
    lines = [json.loads(l) for l in (tmp_path / LOG_FILENAME).read_text().splitlines()]
    assert len(lines) == 2
    assert lines[0]["message"] == "hello x" and lines[0]["book"] == "b"
    assert "ValueError" in lines[1]["exception"]


def test_enabled_via_config(tmp_path, clean_root_logger):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(
        f"data_dir: {tmp_path}/d\naddons:\n  logging:\n    enabled: true\n    dir: {tmp_path}/logs\n"
    )
    cli.main(["--config", str(cfg), "review", "list"])  # any cheap command
    logging.getLogger("x").info("probe")
    for h in clean_root_logger.handlers:
        h.flush()
    assert "probe" in (tmp_path / "logs" / LOG_FILENAME).read_text()


def test_tool_calls_log_metadata_only(tmp_path, config, embeddings, caplog):
    server = build_server(config, embeddings, VectorStore(config.chroma_dir))
    with caplog.at_level(logging.INFO):
        asyncio.run(server.call_tool("search_books", {"query": "SECRET QUERY TEXT"}))
        asyncio.run(server.call_tool("list_books", {}))
    assert "tool=search_books" in caplog.text and "tool=list_books" in caplog.text
    assert "SECRET QUERY TEXT" not in caplog.text
