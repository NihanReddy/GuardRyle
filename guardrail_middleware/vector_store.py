from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .embedding_model import EmbeddingModel


class VectorStore:
    """Simple on-disk vector store for persisted semantic candidate search."""

    def __init__(self, storage_path: str | Path | None = None):
        self.storage_path = Path(storage_path) if storage_path is not None else Path("data/vector_store.json")
        self._documents: list[dict[str, Any]] = []
        self._embedding_model = EmbeddingModel()
        self._load_if_exists()

    def add_document(self, doc_id: str, text: str, metadata: dict[str, Any] | None = None, vector: list[float] | None = None) -> None:
        resolved_vector = vector if vector is not None else self._embedding_model.embed(text)
        document = {
            "id": doc_id,
            "text": text,
            "metadata": metadata or {},
            "vector": resolved_vector,
        }
        self._documents.append(document)

    def persist(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with self.storage_path.open("w", encoding="utf-8") as handle:
            json.dump(self._documents, handle, indent=2)

    def search(self, query_vector: list[float], top_k: int = 3) -> list[dict[str, Any]]:
        if not self._documents:
            return []

        results: list[dict[str, Any]] = []
        for document in self._documents:
            stored_vector = document.get("vector") or []
            if not stored_vector:
                continue
            score = self._cosine_similarity(query_vector, stored_vector)
            results.append({
                "id": document["id"],
                "text": document["text"],
                "score": score,
                "metadata": document.get("metadata", {}),
            })

        results.sort(key=lambda item: item["score"], reverse=True)
        return results[:top_k]

    def _load_if_exists(self) -> None:
        if not self.storage_path.exists():
            return
        with self.storage_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
            if isinstance(payload, list):
                self._documents = payload

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if not left or not right:
            return 0.0

        length = min(len(left), len(right))
        dot = sum(left[i] * right[i] for i in range(length))
        left_norm = math.sqrt(sum(value * value for value in left[:length]))
        right_norm = math.sqrt(sum(value * value for value in right[:length]))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return dot / (left_norm * right_norm)
