"""Resolve entries that the duplicates add-on parked in review/."""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from book_archivar.config import Config
from book_archivar.importer import import_epub
from book_archivar.library import remove_entry
from book_archivar.vectorstore import VectorStore

logger = logging.getLogger(__name__)

ACTIONS = ("keep-both", "replace", "discard")


def list_entries(review_dir: Path) -> list[dict]:
    out = []
    for folder in sorted(p for p in Path(review_dir).glob("*") if p.is_dir()):
        note_path = folder / "note.json"
        note = json.loads(note_path.read_text()) if note_path.exists() else {}
        out.append({"entry": folder.name, "matched_slug": note.get("matched_slug"),
                    "files": [f.name for f in folder.glob("*.epub")]})
    return out


def resolve(
    entry_dir: Path, action: str, config: Config, embeddings_client, vector_store: VectorStore
) -> None:
    """Apply a decision to one review entry.

    - keep-both: import the candidate as an additional book (the slug gets a
      hash suffix, nothing is overwritten).
    - replace: import the candidate, and only after that succeeded remove the
      matched book (directory, vectors, index row). A failed import therefore
      never costs you the old copy.
    - discard: delete the candidate.

    Stop `serve` first: two processes writing the index and Chroma at once is
    not safe.
    """
    entry_dir = Path(entry_dir)
    if action not in ACTIONS:
        raise ValueError(f"unknown action: {action}")
    if action == "discard":
        shutil.rmtree(entry_dir)
        return

    epubs = sorted(entry_dir.glob("*.epub"))
    if len(epubs) != 1:
        raise ValueError(f"expected exactly one .epub in {entry_dir}, found {len(epubs)}")

    matched_slug = None
    if action == "replace":
        note_path = entry_dir / "note.json"
        matched_slug = json.loads(note_path.read_text()).get("matched_slug") if note_path.exists() else None
        if not matched_slug:
            raise ValueError(f"no matched_slug in {entry_dir}/note.json; cannot replace")

    # force=True: skip the duplicate checks that parked this file in the first place.
    outcome = import_epub(epubs[0], config, embeddings_client, vector_store, force=True)
    logger.info("review %s %s -> %s", action, entry_dir.name, outcome.slug)

    if matched_slug:
        shutil.rmtree(config.library_dir / matched_slug, ignore_errors=True)
        vector_store.delete_slug(matched_slug)
        remove_entry(config.library_dir / "index.json", matched_slug)
    shutil.rmtree(entry_dir)
