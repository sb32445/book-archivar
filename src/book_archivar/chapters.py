from __future__ import annotations

import dataclasses
import json
from pathlib import Path


@dataclasses.dataclass(frozen=True)
class Chapter:
    title: str
    start_byte: int
    end_byte: int


def write_chapters(chapters: list[Chapter], path: Path) -> None:
    Path(path).write_text(
        json.dumps([dataclasses.asdict(c) for c in chapters], indent=2, ensure_ascii=False)
    )


def read_chapters(path: Path) -> list[Chapter]:
    return [Chapter(**c) for c in json.loads(Path(path).read_text())]
