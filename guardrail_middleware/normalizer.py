from __future__ import annotations


class RequestNormalizer:
    """Normalizes request and response text before evaluation."""

    @staticmethod
    def normalize(text: str, *, trim: bool = True, collapse_whitespace: bool = True) -> str:
        if text is None:
            return ""

        normalized = text
        if trim:
            normalized = normalized.strip()
        if collapse_whitespace:
            normalized = " ".join(normalized.split())
        return normalized
