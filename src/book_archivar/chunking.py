from __future__ import annotations

import dataclasses
import re

from book_archivar.chapters import Chapter

_SENTENCE_END = re.compile(r"[.!?…»”\"')\]]\s")


@dataclasses.dataclass(frozen=True)
class Chunk:
    text: str
    chapter_title: str
    chunk_index: int
    chapter_index: int = 0


def _cut(text: str, start: int, size: int) -> int:
    """End offset of the chunk starting at `start`: at most `size` characters,
    preferably ending at a paragraph break, else a sentence end, else a space."""
    hard_end = start + size
    if hard_end >= len(text):
        return len(text)
    window_start = start + size // 2  # never produce a tiny chunk just to find a break
    window = text[window_start:hard_end]
    para = window.rfind("\n\n")
    if para != -1:
        return window_start + para + 2
    sentence = None
    for sentence in _SENTENCE_END.finditer(window):
        pass
    if sentence is not None:
        return window_start + sentence.end()
    space = window.rfind(" ")
    if space != -1:
        return window_start + space + 1
    return hard_end


def _word_start(text: str, pos: int, limit: int) -> int:
    """Move `pos` forward to the start of the next word (within `limit`)."""
    if pos == 0 or text[pos - 1].isspace():
        return pos
    for i in range(pos, min(limit, len(text))):
        if text[i].isspace():
            return min(i + 1, limit)
    return pos


def chunk_book(
    body_bytes: bytes, chapters: list[Chapter], size: int = 1500, overlap: int = 200
) -> list[Chunk]:
    """Split every chapter into overlapping chunks that end at paragraph,
    sentence or word boundaries wherever possible. Whitespace-only chunks are
    dropped, they only pollute search results."""
    chunks: list[Chunk] = []
    index = 0
    for chapter_index, chapter in enumerate(chapters):
        text = body_bytes[chapter.start_byte : chapter.end_byte].decode("utf-8", errors="ignore")
        start = 0
        while start < len(text):
            end = _cut(text, start, size)
            piece = text[start:end]
            if piece.strip():
                chunks.append(Chunk(piece, chapter.title, index, chapter_index))
                index += 1
            if end >= len(text):
                break
            nxt = max(end - overlap, start + 1)
            start = _word_start(text, nxt, end)
            if start <= 0 or start >= end:  # no usable overlap: continue where we stopped
                start = end
    return chunks
