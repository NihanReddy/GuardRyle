from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from openai import OpenAI


class ProviderError(RuntimeError):
    """Raised when an embedding provider cannot complete a required check."""


@dataclass(frozen=True, slots=True)
class EmbeddingMetadata:
    provider: str
    model_id: str
    dimensions: int
    execution: str
    metric: str = "cosine"
    normalized: bool = False


class EmbeddingProvider(Protocol):
    @property
    def metadata(self) -> EmbeddingMetadata: ...

    def embed(self, text: str) -> list[float]: ...


class OpenAIEmbeddingProvider:
    """Production remote embedding provider backed by the OpenAI API."""

    def __init__(
        self,
        api_key: str,
        model_id: str = "text-embedding-3-small",
        dimensions: int = 1536,
        timeout_seconds: float = 10.0,
    ):
        if not api_key.strip():
            raise ValueError("OpenAI API key must not be empty.")
        if dimensions <= 0:
            raise ValueError("OpenAI embedding dimensions must be positive.")
        self._client = OpenAI(api_key=api_key, timeout=timeout_seconds)
        self._metadata = EmbeddingMetadata(
            provider="openai",
            model_id=model_id,
            dimensions=dimensions,
            execution="remote",
        )

    @property
    def metadata(self) -> EmbeddingMetadata:
        return self._metadata

    def embed(self, text: str) -> list[float]:
        response = self._client.embeddings.create(
            model=self._metadata.model_id,
            input=text,
        )
        vector = [float(value) for value in response.data[0].embedding]
        if len(vector) != self._metadata.dimensions:
            raise ProviderError("OpenAI returned unexpected embedding dimensions.")
        return vector


class ProviderRegistry:
    """Small registry that selects only explicitly registered healthy providers."""

    def __init__(self) -> None:
        self._providers: dict[str, EmbeddingProvider] = {}
        self._healthy: dict[str, bool] = {}

    def register(self, name: str, provider: EmbeddingProvider, *, healthy: bool = True) -> None:
        if not name.strip():
            raise ValueError("Provider name cannot be empty.")
        self._providers[name] = provider
        self._healthy[name] = healthy

    def set_health(self, name: str, healthy: bool) -> None:
        if name not in self._providers:
            raise KeyError(f"Unknown provider: {name}")
        self._healthy[name] = healthy

    def get(self, name: str) -> EmbeddingProvider:
        if name not in self._providers:
            raise ProviderError(f"Embedding provider '{name}' is unavailable.")
        if not self._healthy.get(name, False):
            raise ProviderError(f"Embedding provider '{name}' is unhealthy.")
        return self._providers[name]

    def select(self, priority: Sequence[str]) -> tuple[str, EmbeddingProvider]:
        for name in priority:
            if name in self._providers and self._healthy.get(name, False):
                return name, self._providers[name]
        raise ProviderError("No healthy embedding provider is available.")

    def status(self) -> list[dict[str, object]]:
        """Return safe provider capabilities without exposing provider secrets."""
        return [
            {
                "id": name,
                "health": "healthy" if self._healthy.get(name, False) else "unhealthy",
                "provider": provider.metadata.provider,
                "model_id": provider.metadata.model_id,
                "dimensions": provider.metadata.dimensions,
                "execution": provider.metadata.execution,
            }
            for name, provider in self._providers.items()
        ]
