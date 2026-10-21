import threading

from book_archivar.addons.inbox import InboxWatcher
from book_archivar.importer import ImportOutcome


def _inbox(tmp_path):
    d = tmp_path / "inbox"
    d.mkdir()
    return d


def test_waits_for_stable_size_then_moves_to_processed(tmp_path):
    inbox = _inbox(tmp_path)
    f = inbox / "b.epub"
    f.write_bytes(b"x" * 10)
    seen = []
    w = InboxWatcher(inbox, lambda p: seen.append(p) or ImportOutcome("imported", "s"))

    w.poll_once()  # first sighting
    f.write_bytes(b"x" * 20)
    w.poll_once()  # still growing
    assert seen == []
    w.poll_once()  # stable
    assert seen == [f]
    assert not f.exists() and (inbox / "processed" / "b.epub").exists()


def test_duplicate_goes_to_duplicates_and_name_clashes_are_kept(tmp_path):
    inbox = _inbox(tmp_path)
    w = InboxWatcher(inbox, lambda p: ImportOutcome("duplicate", "s"))
    for _ in range(2):
        (inbox / "b.epub").write_bytes(b"x")
        w.poll_once(); w.poll_once()
    assert sorted(p.name for p in (inbox / "duplicates").iterdir()) == ["b-1.epub", "b.epub"]


def test_repeated_failure_moves_to_failed_and_nothing_is_deleted(tmp_path):
    inbox = _inbox(tmp_path)
    f = inbox / "bad.epub"
    f.write_bytes(b"x")
    calls = []

    def boom(p):
        calls.append(p)
        raise RuntimeError("boom")

    w = InboxWatcher(inbox, boom, max_attempts=2)
    w.poll_once()
    w.poll_once(); assert f.exists() and len(calls) == 1
    w.poll_once()
    assert len(calls) == 2 and (inbox / "failed" / "bad.epub").exists()


def test_ignores_non_epub_and_subfolders(tmp_path):
    inbox = _inbox(tmp_path)
    (inbox / "notes.txt").write_text("hi")
    (inbox / "sub").mkdir()
    (inbox / "sub" / "x.epub").write_bytes(b"x")
    calls = []
    w = InboxWatcher(inbox, lambda p: calls.append(p))
    for _ in range(3):
        w.poll_once()
    assert calls == []


def test_run_forever_stops_on_event(tmp_path):
    w = InboxWatcher(_inbox(tmp_path), lambda p: None)
    stop = threading.Event()
    t = threading.Thread(target=w.run_forever, args=(0.01, stop))
    t.start(); stop.set(); t.join(2)
    assert not t.is_alive()


def test_watch_imports_real_epub_end_to_end(tmp_path, alice_epub, config, embeddings):
    from book_archivar.importer import import_epub
    from book_archivar.library import read_index
    from book_archivar.vectorstore import VectorStore

    store = VectorStore(config.chroma_dir)
    inbox = _inbox(tmp_path)
    (inbox / "alice.epub").write_bytes(alice_epub.read_bytes())
    w = InboxWatcher(inbox, lambda p: import_epub(p, config, embeddings, store))
    w.poll_once(); w.poll_once()
    assert len(read_index(config.library_dir / "index.json")) == 1
    assert (inbox / "processed" / "alice.epub").exists()


def test_endpoint_outage_never_moves_a_book_to_failed(tmp_path):
    inbox = _inbox(tmp_path)
    f = inbox / "b.epub"
    f.write_bytes(b"x")
    state = {"down": True}

    def flaky(p):
        if state["down"]:
            raise ConnectionRefusedError("embedding endpoint down")
        return ImportOutcome("imported", "s")

    w = InboxWatcher(inbox, flaky, max_attempts=2)
    for _ in range(10):
        w.poll_once()
    assert f.exists() and not (inbox / "failed").exists()

    state["down"] = False
    w.poll_once()
    assert (inbox / "processed" / "b.epub").exists()
