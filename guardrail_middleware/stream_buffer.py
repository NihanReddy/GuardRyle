from __future__ import annotations

from collections import deque
from typing import Any


class StreamBuffer:
    """Rolling text buffer for streaming guardrail evaluation."""

    def __init__(self, max_chunks: int = 10, max_chars: int = 2000):
        self.max_chunks = max_chunks
        self.max_chars = max_chars
        self._buffer: deque[str] = deque(maxlen=max_chunks)

    def append(self, chunk: str) -> None:
        if chunk:
            self._buffer.append(chunk)

    def build_text(self) -> str:
        text = "".join(self._buffer)
        if len(text) > self.max_chars:
            return text[-self.max_chars :]
        return text

    def clear(self) -> None:
        self._buffer.clear()

    def __len__(self) -> int:
        return len(self._buffer)
