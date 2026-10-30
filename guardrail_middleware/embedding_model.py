from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


class EmbeddingModel:
    """Real sentence embedding model wrapper with a lightweight fallback for reliability."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model: "SentenceTransformer | None" = None
        self._fallback_dimension = 384

    def _load_model(self) -> "SentenceTransformer":
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError("sentence-transformers is not installed.") from exc
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed(self, text: str) -> list[float]:
        cleaned = (text or "").strip()
        if not cleaned:
            return [0.0] * self._fallback_dimension

        try:
            model = self._load_model()
            vector = model.encode(cleaned, convert_to_numpy=True)
            return [float(value) for value in vector.tolist()]
        except (ImportError, RuntimeError, OSError, ValueError):
            return self._fallback_embedding(cleaned)

    def _fallback_embedding(self, text: str) -> list[float]:
        values = [0.0] * self._fallback_dimension
        for index, token in enumerate(text.lower().split()):
            if index >= self._fallback_dimension:
                break
            value = sum(ord(char) for char in token) / max(len(token), 1)
            values[index] = float(value / 1000.0)
        return values
