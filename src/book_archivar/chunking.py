from __future__ import annotations

import dataclasses

from book_archivar.chapters import Chapter


@dataclasses.dataclass(frozen=True)
class Chunk:
    text: str
    chapter_title: str
    chunk_index: int


def chunk_book(
    body_bytes: bytes, chapters: list[Chapter], size: int = 1500, overlap: int = 200
) -> list[Chunk]:
    chunks: list[Chunk] = []
    index = 0
    for chapter in chapters:
        chapter_bytes = body_bytes[chapter.start_byte : chapter.end_byte]
        chapter_text = chapter_bytes.decode("utf-8", errors="ignore")
        i = 0
        step = max(size - overlap, 1)
        while i < len(chapter_text):
            piece = chapter_text[i : i + size]
            if piece.strip():  # whitespace-only chunks only pollute search results
                chunks.append(
                    Chunk(text=piece, chapter_title=chapter.title, chunk_index=index)
                )
                index += 1
            i += step
    return chunks
