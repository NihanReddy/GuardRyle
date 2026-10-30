from __future__ import annotations

import os
import json
import hmac
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from openai import APIError, OpenAI
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import RuntimeConfig
from .credentials import CredentialStore, CredentialStoreError
from .embedding_model import EmbeddingModel
from .decision_engine import DecisionEngine
from .providers import EmbeddingMetadata, EmbeddingProvider, OpenAIEmbeddingProvider, ProviderError, ProviderRegistry
from .operational_store import OperationalStore
from .policy_config import PolicyConfigLoader
from .models import Decision, Policy
from .security import AuditEvent, SecurityPipeline
from .semantic_engine import SemanticEngine
from .vector_store import VectorStore

DEFAULT_LOCAL_PROVIDER = "local"
DEFAULT_LOCAL_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class LocalEmbeddingProvider:
    """Provider adapter for GuardRyle's default local embedding model."""

    def __init__(self, model_id: str = DEFAULT_LOCAL_MODEL):
        self._model = EmbeddingModel(model_id)
        self._metadata = {
            "provider": DEFAULT_LOCAL_PROVIDER,
            "model_id": model_id,
            "dimensions": 384,
            "execution": "local",
        }

    @property
    def metadata(self) -> Any:
        from .providers import EmbeddingMetadata

        return EmbeddingMetadata(**self._metadata)

    def embed(self, text: str) -> list[float]:
        return self._model.embed(text)


class ProviderConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=300)


class OpenAIKeyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: str = Field(min_length=1, max_length=500)

    @field_validator("api_key")
    @classmethod
    def reject_control_characters(cls, value: str) -> str:
        if any(character in value for character in value if ord(character) < 32):
            raise ValueError("API key contains invalid characters.")
        return value


class EvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=20_000)
    required_security_check: bool = False
    policy_id: str | None = Field(default=None, min_length=1, max_length=200)


@dataclass(slots=True)
class RuntimeState:
    registry: ProviderRegistry
    config: RuntimeConfig
    admin_token: str | None = None
    allowed_origins: Sequence[str] = field(default_factory=tuple)
    openai_key: str | None = None
    configured_provider: str | None = None
    configured_model: str | None = None
    active_provider: str | None = None
    active_model: str | None = None
    degraded: bool = False
    security_evaluation_required: bool = False
    security_evaluation_available: bool = True
    openai_connection: str = "unknown"
    openai_error: str | None = None
    openai_test: Callable[[str], int] | None = None
    credential_store: CredentialStore = field(default_factory=CredentialStore)
    vector_store: VectorStore | None = None
    security_pipeline: SecurityPipeline | None = None
    configuration_valid: bool = True
    configuration_error: str | None = None
    operational_store: OperationalStore = field(
        default_factory=lambda: OperationalStore(
            os.getenv("GUARDRYLE_RUNTIME_DB", "data/guardryle_runtime.sqlite3")
        )
    )
    policy: Policy | None = None

    def __post_init__(self) -> None:
        if self.openai_key is None:
            self.openai_key = os.getenv("OPENAI_API_KEY")
            if self.openai_key is None:
                try:
                    self.openai_key = self.credential_store.get()
                except CredentialStoreError:
                    self.openai_error = "Secure credential storage is unavailable."
        if self.configured_provider is None:
            self.configured_provider = self.config.primary_provider or None
        self._sync_configured_model()
        if self.security_pipeline is None:
            self.security_pipeline = SecurityPipeline(DecisionEngine(), self.config)
        if self.security_pipeline is not None:
            self.security_pipeline.audit_sink = self.record_security_event
        if self.policy is None:
            self.policy = _load_default_policy()

    def _sync_configured_model(self) -> None:
        if self.configured_provider is None:
            return
        self.configuration_valid = False
        self.configuration_error = "Configured embedding provider is unavailable."
        for item in self.registry.status():
            if item["id"] == self.configured_provider:
                self.configured_model = str(item["model_id"])
                if item["health"] == "healthy":
                    self.configuration_valid = True
                    self.configuration_error = None
                return

    def provider_status(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for item in self.registry.status():
            result.append({
                "id": item["id"],
                "label": str(item["provider"]),
                "execution": item["execution"],
                "health": item["health"],
                "supportedModels": [{
                    "id": item["model_id"],
                    "dimensions": item["dimensions"],
                }],
            })
        return result

    def embedding_status(self) -> dict[str, Any]:
        item = next(
            (entry for entry in self.registry.status() if entry["id"] == self.active_provider),
            None,
        )
        if item is None:
            item = next(
                (entry for entry in self.registry.status() if entry["id"] == self.configured_provider),
                None,
            )
        dimensions = item["dimensions"] if item else None
        execution = item["execution"] if item else "unknown"
        health = item["health"] if item else "unknown"
        if self.configured_provider and item is None:
            health = "unknown"
        return {
            "configuredProvider": self.configured_provider,
            "configuredModel": self.configured_model,
            "activeProvider": self.active_provider,
            "activeModel": self.active_model,
            "dimensions": dimensions,
            "execution": execution,
            "providerHealth": health,
            "degraded": self.degraded,
            "securityEvaluationRequired": self.security_evaluation_required,
            "securityEvaluationAvailable": self.security_evaluation_available,
            "error": None if health != "unhealthy" else "Configured provider is unhealthy.",
            "configurationValid": self.configuration_valid,
            "configurationError": self.configuration_error,
        }

    def select_provider(self, provider_name: str, model_id: str) -> None:
        try:
            provider = self.registry.get(provider_name)
        except (KeyError, ProviderError) as exc:
            raise ValueError("Requested provider is unavailable.") from exc
        metadata = provider.metadata
        if metadata.model_id != model_id:
            raise ValueError("Requested model is not registered for this provider.")
        if metadata.dimensions <= 0:
            raise ValueError("Provider reported invalid embedding dimensions.")
        self.configured_provider = provider_name
        self.configured_model = metadata.model_id
        self.active_provider = provider_name
        self.active_model = metadata.model_id
        self.degraded = False
        self.configuration_valid = True
        self.configuration_error = None

    def set_openai_key(self, api_key: str) -> None:
        try:
            self.credential_store.set(api_key)
        except CredentialStoreError as exc:
            raise ValueError("Secure credential storage is unavailable.") from exc
        self.openai_key = api_key
        self.openai_connection = "unknown"
        self.openai_error = None

    def test_openai(self) -> None:
        if not self.openai_key:
            self.openai_connection = "failed"
            self.openai_error = "OpenAI credentials are not configured."
            raise ValueError(self.openai_error)
        try:
            model_id = os.getenv("OPENAI_EMBEDDING_MODEL") or self.configured_model
            if self.openai_test is None:
                if not model_id:
                    raise ValueError("OPENAI_EMBEDDING_MODEL is not configured.")
                client = OpenAI(api_key=self.openai_key, timeout=self.config.remote_timeout_seconds)
                response = client.embeddings.create(
                    model=model_id,
                    input="guardryle health check",
                )
                dimensions = len(response.data[0].embedding)
            else:
                dimensions = self.openai_test(self.openai_key)
            if dimensions <= 0:
                raise ValueError("OpenAI returned invalid embedding dimensions.")
            expected_metadata = self.vector_store.model_metadata if self.vector_store else None
            if expected_metadata is not None:
                if model_id != expected_metadata.model_id:
                    raise ValueError("OpenAI model does not match the embedding index.")
                if dimensions != expected_metadata.dimensions:
                    raise ValueError("OpenAI dimensions do not match the embedding index.")
        except (APIError, OSError, RuntimeError, TimeoutError, ValueError) as exc:
            self.openai_connection = "failed"
            self.openai_error = "OpenAI connection test failed."
            raise ValueError(self.openai_error) from exc
        self.openai_connection = "connected"
        self.openai_error = None

    def record_security_event(self, event: AuditEvent) -> None:
        self.operational_store.record(event)
        if event.provider_used:
            self.active_provider = event.provider_used
            self.active_model = self.configured_model

    def record_embedding_request(self, provider_name: str, model_id: str) -> None:
        provider = self.registry.get(provider_name)
        if provider.metadata.model_id != model_id:
            raise ValueError("Embedding request model does not match the configured provider.")
        self.active_provider = provider_name
        self.active_model = model_id

    def openai_status(self) -> dict[str, Any]:
        return {
            "configured": bool(self.openai_key),
            "connection": self.openai_connection,
            "error": self.openai_error,
        }

    def evaluate(self, payload: EvaluationRequest) -> dict[str, Any]:
        if self.policy is None:
            raise ValueError("No policy is configured.")
        if payload.policy_id and payload.policy_id != self.policy.id:
            raise ValueError("Requested policy is unavailable.")
        if self.security_pipeline is None:
            raise ValueError("Security evaluation is not configured.")
        provider_used = self.active_provider or self.configured_provider
        result = self.security_pipeline.evaluate(
            payload.text,
            self.policy,
            required_semantic_check=payload.required_security_check,
            provider_used=provider_used,
        )
        return {
            "decision": result.decision.value,
            "reasons": result.reasons,
            "rule_hits": result.rule_hits,
            "metadata": {
                "request_id": result.metadata.get("request_id"),
                "provider_used": result.metadata.get("provider_used"),
                "degraded_mode": result.metadata.get("degraded_mode", False),
                "latency_ms": result.metadata.get("latency_ms"),
            },
        }

    def dashboard(self) -> dict[str, Any]:
        summary = self.operational_store.summary()
        events = self.operational_store.recent()
        live_findings = [
            {
                "id": event["request_id"],
                "prompt": "[redacted]",
                "category": "runtime evaluation",
                "policy": self.policy.id if self.policy else "unknown",
                "expected": "runtime",
                "observed": event["decision"],
                "kind": "runtime_event",
                "latencyMs": event["latency_ms"],
                "source": "operational_store",
                "reasonCode": event["reason_code"],
                "provider": event["provider_used"],
                "degraded": bool(event["degraded_mode"]),
                "reviewed": bool(event["reviewed"]),
                "createdAt": event["created_at"],
            }
            for event in events
        ]
        return {
            "live": True,
            "lastUpdated": summary["last_event_at"],
            "source": {
                "policy": "active runtime policy",
                "dataset": "runtime audit events",
                "report": "operational store",
            },
            "policy": {
                "id": self.policy.id if self.policy else None,
                "name": self.policy.name if self.policy else "No policy configured",
                "defaultDecision": self.policy.default_decision.value if self.policy else None,
                "rules": len(self.policy.rules) if self.policy else 0,
                "semanticExamples": len(self.policy.semantic_examples) if self.policy else 0,
                "semanticDenyThreshold": self.policy.semantic_deny_threshold if self.policy else None,
                "semanticReviewThreshold": self.policy.semantic_review_threshold if self.policy else None,
            },
            "runtime": {
                "total": summary["total"],
                "blocked": summary["denied"],
                "review": summary["review"],
                "allowed": summary["allowed"],
                "degraded": summary["degraded"],
                "reviewed": summary["reviewed"],
                "averageLatencyMs": summary["average_latency_ms"],
                "lastEventAt": summary["last_event_at"],
            },
            "findings": live_findings,
        }


def create_app(
    *,
    state: RuntimeState | None = None,
    registry: ProviderRegistry | None = None,
    config: RuntimeConfig | None = None,
    admin_token: str | None = None,
    allowed_origins: Sequence[str] | None = None,
    vector_store: VectorStore | None = None,
    security_pipeline: SecurityPipeline | None = None,
) -> FastAPI:
    selected_config = config or _load_runtime_config()
    selected_registry = registry
    if selected_registry is None:
        selected_registry = ProviderRegistry()
        selected_registry.register(
            DEFAULT_LOCAL_PROVIDER,
            LocalEmbeddingProvider(selected_config.local_fallback_model or DEFAULT_LOCAL_MODEL),
        )
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            openai_model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
            openai_dimensions = int(os.getenv("OPENAI_EMBEDDING_DIMENSIONS", "1536"))
            selected_registry.register(
                "openai",
                OpenAIEmbeddingProvider(
                    openai_key,
                    model_id=openai_model,
                    dimensions=openai_dimensions,
                    timeout_seconds=selected_config.remote_timeout_seconds,
                ),
            )
    semantic_provider: EmbeddingProvider | None = None
    try:
        semantic_provider = selected_registry.get(selected_config.primary_provider)
    except ProviderError:
        pass
    selected_pipeline = security_pipeline or SecurityPipeline(
        DecisionEngine(semantic_engine=SemanticEngine(semantic_provider)),
        selected_config,
    )
    runtime = state or RuntimeState(
        registry=selected_registry,
        config=selected_config,
        admin_token=admin_token if admin_token is not None else os.getenv("GUARDRYLE_ADMIN_TOKEN"),
        allowed_origins=allowed_origins or _configured_origins(),
        vector_store=vector_store,
        security_pipeline=selected_pipeline,
    )
    app = FastAPI(title="GuardRyle API", docs_url=None, redoc_url=None)
    app.state.runtime = runtime

    @app.middleware("http")
    async def request_context(request: Request, call_next: Callable[..., Any]) -> Any:
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    origins = list(runtime.allowed_origins)
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=False,
            allow_methods=["GET", "PUT", "POST"],
            allow_headers=["Authorization", "Content-Type"],
        )

    @app.exception_handler(ValueError)
    async def handle_value_error(_: Request, __: ValueError) -> Any:
        return _json_error(status.HTTP_400_BAD_REQUEST, "Invalid configuration.")

    @app.get("/health/live")
    async def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def readiness() -> Any:
        checks = {
            "policy": runtime.policy is not None,
            "provider": runtime.configuration_valid,
            "admin_auth": bool(runtime.admin_token),
        }
        if all(checks.values()):
            return {"status": "ready", "checks": checks}
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready", "checks": checks},
        )

    @app.get("/api/embedding/status")
    async def embedding_status() -> dict[str, Any]:
        return runtime.embedding_status()

    @app.get("/api/dashboard")
    async def dashboard() -> dict[str, Any]:
        return runtime.dashboard()

    @app.post("/api/dashboard/events/{request_id}/review")
    async def review_event(
        request_id: str,
        _: None = Depends(require_admin(runtime)),
    ) -> dict[str, Any]:
        if not runtime.operational_store.mark_reviewed(request_id):
            raise HTTPException(status_code=404, detail="Runtime event was not found.")
        return {"request_id": request_id, "reviewed": True}

    @app.post("/api/evaluate")
    async def evaluate(
        payload: EvaluationRequest,
        _: None = Depends(require_admin(runtime)),
    ) -> dict[str, Any]:
        return runtime.evaluate(payload)

    @app.get("/api/embedding/providers")
    async def embedding_providers() -> list[dict[str, Any]]:
        return runtime.provider_status()

    @app.put("/api/embedding/config")
    async def embedding_config(
        payload: ProviderConfigRequest,
        _: None = Depends(require_admin(runtime)),
    ) -> dict[str, Any]:
        runtime.select_provider(payload.provider, payload.model)
        return runtime.embedding_status()

    @app.get("/api/providers/openai/status")
    async def openai_status() -> dict[str, Any]:
        return runtime.openai_status()

    @app.put("/api/providers/openai/key")
    async def openai_key(
        payload: OpenAIKeyRequest,
        _: None = Depends(require_admin(runtime)),
    ) -> dict[str, Any]:
        runtime.set_openai_key(payload.api_key)
        return runtime.openai_status()

    @app.post("/api/providers/openai/test")
    async def openai_test(
        _: None = Depends(require_admin(runtime)),
    ) -> dict[str, Any]:
        runtime.test_openai()
        return runtime.openai_status()

    return app


# Authenticate administrative requests against the configured server-side token.
def require_admin(runtime: RuntimeState) -> Callable[..., None]:
    async def dependency(authorization: str | None = Header(default=None)) -> None:
        if not runtime.admin_token:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Administrative API is not configured.",
            )
        expected = f"Bearer {runtime.admin_token}"
        if not authorization or not hmac.compare_digest(authorization, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Administrative authorization required.",
                headers={"WWW-Authenticate": "Bearer"},
            )
    return dependency


def _configured_origins() -> tuple[str, ...]:
    value = os.getenv("GUARDRYLE_CORS_ORIGINS", "")
    return tuple(origin.strip() for origin in value.split(",") if origin.strip())


def _load_runtime_config() -> RuntimeConfig:
    configured_path = os.getenv("GUARDRYLE_CONFIG_PATH")
    if configured_path:
        return RuntimeConfig.load_file(configured_path)
    default_path = "guardrail_config.json"
    if os.path.exists(default_path):
        return RuntimeConfig.load_file(default_path)
    return RuntimeConfig()


def _load_default_policy() -> Policy | None:
    policy_path = os.getenv("GUARDRYLE_POLICY_PATH", "policy.json")
    try:
        policies = PolicyConfigLoader.load_file(policy_path)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return policies[0] if policies else None


def _json_error(code: int, message: str) -> Any:
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=code, content={"detail": message})


app = create_app()
