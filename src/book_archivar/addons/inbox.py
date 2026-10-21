"""Add-on: watch a folder and import every EPUB dropped into it.

Files are never deleted. After handling, each file moves into a subfolder of the
inbox: processed/ (imported), duplicates/ (already in the library) or failed/
(the file itself is broken: still failing after MAX_ATTEMPTS polls).
Network/OS errors such as an unreachable embedding endpoint never count: the
file stays in the inbox until the problem is fixed.
"""
from __future__ import annotations

import logging
import shutil
import threading
from pathlib import Path
from typing import Callable

from book_archivar.importer import ImportOutcome

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
_DESTINATIONS = {"imported": "processed", "duplicate": "duplicates"}


class InboxWatcher:
    def __init__(
        self,
        inbox_dir: Path,
        import_fn: Callable[[Path], ImportOutcome],
        max_attempts: int = MAX_ATTEMPTS,
    ):
        self._inbox = Path(inbox_dir)
        self._inbox.mkdir(parents=True, exist_ok=True)
        self._import_fn = import_fn
        self._max_attempts = max_attempts
        self._last_size: dict[str, int] = {}
        self._attempts: dict[str, int] = {}

    def poll_once(self) -> None:
        epubs = [f for f in self._inbox.iterdir() if f.is_file() and f.suffix.lower() == ".epub"]
        present = {f.name for f in epubs}
        for state in (self._last_size, self._attempts):
            for name in set(state) - present:
                del state[name]
        for epub in sorted(epubs):
            self._handle(epub)

    def _handle(self, epub: Path) -> None:
        size = epub.stat().st_size
        previous = self._last_size.get(epub.name)
        self._last_size[epub.name] = size
        if previous != size:
            return  # first sighting or still being copied: wait for a stable size

        try:
            outcome = self._import_fn(epub)
        except OSError as exc:
            # Embedding endpoint down, network hiccup, disk trouble: not the
            # book's fault. Keep it in the inbox and retry on the next poll,
            # without counting towards MAX_ATTEMPTS.
            logger.warning("import of %s postponed: %s", epub.name, exc)
            return
        except Exception:
            attempt = self._attempts.get(epub.name, 0) + 1
            self._attempts[epub.name] = attempt
            logger.exception("import failed for %s (attempt %d)", epub.name, attempt)
            if attempt >= self._max_attempts:
                self._move(epub, "failed")
            return
        logger.info("inbox %s -> %s (%s)", epub.name, outcome.status, outcome.slug)
        self._move(epub, _DESTINATIONS.get(outcome.status, "processed"))

    def _move(self, epub: Path, subdir: str) -> None:
        target_dir = self._inbox / subdir
        target_dir.mkdir(exist_ok=True)
        target = target_dir / epub.name
        n = 1
        while target.exists():
            target = target_dir / f"{epub.stem}-{n}{epub.suffix}"
            n += 1
        shutil.move(str(epub), str(target))
        self._last_size.pop(epub.name, None)
        self._attempts.pop(epub.name, None)

    def run_forever(self, poll_seconds: float, stop: threading.Event | None = None) -> None:
        stop = stop or threading.Event()
        while not stop.is_set():
            try:
                self.poll_once()
            except Exception:
                logger.exception("inbox poll failed")
            stop.wait(poll_seconds)
