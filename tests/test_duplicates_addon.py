import json

import pytest

from book_archivar import cli
from book_archivar.addons import review
from book_archivar.addons.duplicates import find_fuzzy_duplicate
from book_archivar.addons.inbox import InboxWatcher
from book_archivar.importer import import_epub
from book_archivar.library import BookEntry, read_index
from book_archivar.vectorstore import VectorStore
from tests.helpers import make_epub


def _two_variants(tmp_path):
    # same author+title, different bytes (one is single-file)
    return (make_epub(tmp_path / "a.epub", title="The Book", author="Doe, Jane"),
            make_epub(tmp_path / "b.epub", title="The Book", author="Jane Doe", single_file=True))


@pytest.fixture
def store(config):
    return VectorStore(config.chroma_dir)


def test_fuzzy_match_ignores_name_order_case_and_edition():
    e = BookEntry("s", "Dune: 2. Auflage", "Herbert, Frank", "de", "h", "t")
    assert find_fuzzy_duplicate("Frank Herbert", "DUNE", [e]) is e
    assert find_fuzzy_duplicate("Frank Herbert", "Dune Messiah", [e]) is None


def test_off_by_default_both_versions_are_imported(tmp_path, config, embeddings, store):
    a, b = _two_variants(tmp_path)
    assert import_epub(a, config, embeddings, store).status == "imported"
    assert import_epub(b, config, embeddings, store).status == "imported"


def test_with_review_dir_the_second_version_is_parked(tmp_path, config, embeddings, store):
    a, b = _two_variants(tmp_path)
    rd = tmp_path / "review"
    first = import_epub(a, config, embeddings, store, review_dir=rd)
    second = import_epub(b, config, embeddings, store, review_dir=rd)
    assert (second.status, second.slug) == ("review", first.slug)
    assert len(read_index(config.library_dir / "index.json")) == 1
    assert b.exists()  # source untouched
    entry = next(rd.iterdir())
    assert json.loads((entry / "note.json").read_text())["matched_slug"] == first.slug
    assert (entry / "b.epub").exists()


def _parked(tmp_path, config, embeddings, store):
    a, b = _two_variants(tmp_path)
    rd = tmp_path / "review"
    first = import_epub(a, config, embeddings, store, review_dir=rd)
    import_epub(b, config, embeddings, store, review_dir=rd)
    return first.slug, next(rd.iterdir())


def test_keep_both(tmp_path, config, embeddings, store):
    old, entry = _parked(tmp_path, config, embeddings, store)
    review.resolve(entry, "keep-both", config, embeddings, store)
    slugs = {e.slug for e in read_index(config.library_dir / "index.json")}
    assert old in slugs and len(slugs) == 2 and not entry.exists()


def test_replace_removes_old_only_after_new_import(tmp_path, config, embeddings, store):
    old, entry = _parked(tmp_path, config, embeddings, store)

    class Broken:
        def embed(self, texts):
            raise ConnectionError("down")

    with pytest.raises(ConnectionError):
        review.resolve(entry, "replace", config, Broken(), store)
    assert (config.library_dir / old).exists() and entry.exists()  # nothing lost

    review.resolve(entry, "replace", config, embeddings, store)
    slugs = {e.slug for e in read_index(config.library_dir / "index.json")}
    assert old not in slugs and len(slugs) == 1
    assert not (config.library_dir / old).exists() and not entry.exists()
    assert store.query(embeddings.embed(["x"])[0], top_k=50, slug=old) == []


def test_discard(tmp_path, config, embeddings, store):
    old, entry = _parked(tmp_path, config, embeddings, store)
    review.resolve(entry, "discard", config, embeddings, store)
    assert not entry.exists() and len(read_index(config.library_dir / "index.json")) == 1


def test_list_and_unknown_action(tmp_path, config, embeddings, store):
    old, entry = _parked(tmp_path, config, embeddings, store)
    assert review.list_entries(entry.parent)[0]["matched_slug"] == old
    with pytest.raises(ValueError):
        review.resolve(entry, "bogus", config, embeddings, store)


def test_watcher_moves_suspects_to_review_subfolder(tmp_path, config, embeddings, store):
    a, b = _two_variants(tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    rd = tmp_path / "review"
    import_epub(a, config, embeddings, store, review_dir=rd)
    (inbox / "b.epub").write_bytes(b.read_bytes())
    w = InboxWatcher(inbox, lambda p: import_epub(p, config, embeddings, store, review_dir=rd))
    w.poll_once(); w.poll_once()
    assert (inbox / "review" / "b.epub").exists()


def test_cli_review_requires_enabled_addon(tmp_path, capsys):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(f"data_dir: {tmp_path}/d\n")
    assert cli.main(["--config", str(cfg), "review", "list"]) == 1
    cfg.write_text(f"data_dir: {tmp_path}/d\naddons:\n  duplicates:\n    enabled: true\n")
    assert cli.main(["--config", str(cfg), "review", "list"]) == 0


def test_non_epub_review_entries_can_be_resolved(tmp_path, config, embeddings, store):
    a = tmp_path / "a.md"
    a.write_text("# Same Title\n\nfirst version")
    b = tmp_path / "b.md"
    b.write_text("# Same Title\n\nsecond version")
    rd = tmp_path / "review"
    first = import_epub(a, config, embeddings, store, review_dir=rd)
    assert import_epub(b, config, embeddings, store, review_dir=rd).status == "review"
    entry = next(rd.iterdir())
    assert review.list_entries(rd)[0]["files"] == ["b.md"]
    review.resolve(entry, "keep-both", config, embeddings, store)
    assert len(read_index(config.library_dir / "index.json")) == 2 and not entry.exists()
