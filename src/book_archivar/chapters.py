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


def chapters_from_boundaries(body: str, boundaries: list[tuple[int, str]]) -> list[Chapter]:
    """Turn (character offset, title) chapter starts into Chapters with byte ranges.

    `boundaries` must be sorted by offset. Text before the first boundary stays
    reachable as "Front matter"; without boundaries the whole text is one chapter.
    """
    boundaries = list(boundaries)
    if boundaries and boundaries[0][0] > 0 and body[: boundaries[0][0]].strip():
        boundaries.insert(0, (0, "Front matter"))
    if not boundaries:
        boundaries = [(0, "Full text")]

    # Convert character offsets to byte offsets in one incremental pass.
    byte_at: dict[int, int] = {}
    prev_char, prev_byte = 0, 0
    for pos in [p for p, _ in boundaries] + [len(body)]:
        prev_byte += len(body[prev_char:pos].encode("utf-8"))
        prev_char = pos
        byte_at[pos] = prev_byte

    ends = [p for p, _ in boundaries[1:]] + [len(body)]
    return [
        Chapter(title=title, start_byte=byte_at[pos], end_byte=byte_at[end])
        for (pos, title), end in zip(boundaries, ends)
    ]
