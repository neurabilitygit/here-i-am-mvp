from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Chunk:
    text: str
    index: int
    start_word: int
    end_word: int


def chunk_text(text: str, chunk_size: int = 220, overlap: int = 40) -> list[Chunk]:
    words = text.split()
    if not words:
        return []

    chunks: list[Chunk] = []
    step = max(1, chunk_size - overlap)
    index = 0
    for start in range(0, len(words), step):
        end = min(len(words), start + chunk_size)
        chunk_words = words[start:end]
        if not chunk_words:
            continue
        chunks.append(
            Chunk(
                text=' '.join(chunk_words),
                index=index,
                start_word=start,
                end_word=end,
            )
        )
        index += 1
        if end >= len(words):
            break
    return chunks
