import pytest

from fastapi.testclient import TestClient

from guardrail_middleware import (
    Decision,
    EmbeddingMetadata,
    GuardrailResult,
    Policy,
    ProviderRegistry,
    RuntimeConfig,
    SecurityPipeline,
    VectorStore,
)
from guardrail_middleware.api import RuntimeState, create_app
from guardrail_middleware.operational_store import OperationalStore


class FakeProvider:
    def __init__(self, model_id: str = "local-test", dimensions: int = 3):
        self.metadata = EmbeddingMetadata("local", model_id, dimensions, "local")

    def embed(self, text: str) -> list[float]:
        return [1.0] * self.metadata.dimensions


class MemoryCredentialStore:
    def __init__(self):
        self.secret = None

    def get(self):
        return self.secret

    def set(self, secret):
        self.secret = secret


def make_client(*, token: str | None = "test-admin", provider: FakeProvider | None = None, tmp_path=None):
    registry = ProviderRegistry()
    if provider is not None:
        registry.register("local", provider)
    state = RuntimeState(
        registry,
        RuntimeConfig(primary_provider="local"),
        admin_token=token,
        credential_store=MemoryCredentialStore(),
        operational_store=OperationalStore(tmp_path / "runtime.sqlite3") if tmp_path else OperationalStore(":memory:"),
    )
    return TestClient(create_app(state=state)), state


def test_embedding_status_reports_unavailable_without_registered_provider():
    client, _ = make_client(provider=None)

    response = client.get("/api/embedding/status")

    assert response.status_code == 200
    assert response.json()["activeModel"] is None
    assert response.json()["providerHealth"] == "unknown"
    assert response.json()["configurationValid"] is False


def test_default_app_uses_local_all_minilm_model():
    client = TestClient(create_app(admin_token="test-admin"))

    status = client.get("/api/embedding/status").json()
    providers = client.get("/api/embedding/providers").json()

    assert status["configuredProvider"] == "local"
    assert status["configuredModel"] == "sentence-transformers/all-MiniLM-L6-v2"
    assert status["activeModel"] is None
    assert status["dimensions"] == 384
    assert status["execution"] == "local"
    assert status["providerHealth"] == "healthy"
    assert providers[0]["supportedModels"][0]["dimensions"] == 384


def test_evaluate_route_persists_sanitized_event_and_dashboard_reads_it(tmp_path):
    registry = ProviderRegistry()
    registry.register("local", FakeProvider())
    state = RuntimeState(
        registry,
        RuntimeConfig(primary_provider="local"),
        admin_token="test-admin",
        credential_store=MemoryCredentialStore(),
        operational_store=OperationalStore(tmp_path / "runtime.sqlite3"),
    )
    client = TestClient(create_app(state=state))

    response = client.post(
        "/api/evaluate",
        headers={"Authorization": "Bearer test-admin"},
        json={"text": "safe request", "required_security_check": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] in {"allow", "deny", "review"}
    assert "safe request" not in response.text
    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    assert any(item["id"] == body["metadata"]["request_id"] for item in dashboard.json()["findings"])
    dashboard_body = dashboard.json()
    assert dashboard_body["live"] is True
    assert dashboard_body["runtime"]["total"] == 1
    assert dashboard_body["source"]["report"] == "operational store"
    assert all(item["source"] == "operational_store" for item in dashboard_body["findings"])

def test_provider_metadata_and_configuration_require_authentication():
    client, _ = make_client(provider=FakeProvider())

    assert client.get("/api/embedding/providers").json()[0]["supportedModels"][0]["dimensions"] == 3
    response = client.put(
        "/api/embedding/config",
        json={"provider": "local", "model": "local-test"},
    )
    assert response.status_code == 401

    response = client.put(
        "/api/embedding/config",
        headers={"Authorization": "Bearer test-admin"},
        json={"provider": "local", "model": "local-test"},
    )
    assert response.status_code == 200
    assert response.json()["activeModel"] == "local-test"


def test_configuration_rejects_unknown_model_and_malformed_payload():
    client, _ = make_client(provider=FakeProvider())
    headers = {"Authorization": "Bearer test-admin"}

    response = client.put(
        "/api/embedding/config",
        headers=headers,
        json={"provider": "local", "model": "different-model"},
    )
    assert response.status_code == 400
    assert "different-model" not in response.text

    response = client.put(
        "/api/embedding/config",
        headers=headers,
        json={"provider": "local", "model": "local-test", "dimensions": 3},
    )
    assert response.status_code == 422


def test_openai_key_is_redacted_and_secret_routes_are_protected():
    client, state = make_client(provider=FakeProvider())
    secret = "sk-test-secret"

    assert client.get("/api/providers/openai/status").json() == {
        "configured": False,
        "connection": "unknown",
        "error": None,
    }
    response = client.put(
        "/api/providers/openai/key",
        headers={"Authorization": "Bearer test-admin"},
        json={"api_key": secret},
    )
    assert response.status_code == 200
    assert secret not in response.text
    assert state.openai_key == secret

    response = client.put(
        "/api/providers/openai/key",
        json={"api_key": secret},
    )
    assert response.status_code == 401


def test_openai_connection_timeout_is_sanitized():
    client, state = make_client(provider=FakeProvider())
    state.set_openai_key("sk-test")

    def timeout(_: str) -> int:
        raise TimeoutError("provider internals must not escape")

    state.openai_test = timeout
    response = client.post(
        "/api/providers/openai/test",
        headers={"Authorization": "Bearer test-admin"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid configuration."}
    assert state.openai_connection == "failed"
    assert "provider internals" not in response.text


def test_openai_connection_success_is_reported_only_after_backend_confirmation():
    client, state = make_client(provider=FakeProvider())
    state.set_openai_key("sk-test")
    state.openai_test = lambda _: 3

    response = client.post(
        "/api/providers/openai/test",
        headers={"Authorization": "Bearer test-admin"},
    )

    assert response.status_code == 200
    assert response.json() == {"configured": True, "connection": "connected", "error": None}


def test_openai_connection_rejects_model_or_dimension_mismatch(tmp_path, monkeypatch):
    registry = ProviderRegistry()
    vector_store = VectorStore(
        tmp_path / "vectors.json",
        model_metadata=EmbeddingMetadata("openai", "text-embedding-3-small", 3, "remote"),
    )
    state = RuntimeState(
        registry,
        RuntimeConfig(primary_provider="local"),
        admin_token="test-admin",
        vector_store=vector_store,
        credential_store=MemoryCredentialStore(),
    )
    state.set_openai_key("sk-test")
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    state.openai_test = lambda _: 4

    with pytest.raises(ValueError, match="OpenAI connection test failed"):
        state.test_openai()
    assert state.openai_connection == "failed"


def test_security_audit_updates_active_provider():
    registry = ProviderRegistry()
    registry.register("local", FakeProvider())
    pipeline = SecurityPipeline(
        type("HealthyEngine", (), {
            "decide": lambda self, text, policy: GuardrailResult(decision=Decision.ALLOW)
        })()
    )
    state = RuntimeState(
        registry,
        RuntimeConfig(primary_provider="local"),
        security_pipeline=pipeline,
    )

    pipeline.evaluate(
        "safe request",
        Policy(id="p", name="p", default_decision=Decision.ALLOW),
        provider_used="local",
    )

    assert state.embedding_status()["activeProvider"] == "local"
    assert state.embedding_status()["activeModel"] == "local-test"


def test_admin_api_requires_configured_token():
    client, _ = make_client(token=None, provider=FakeProvider())

    response = client.put(
        "/api/providers/openai/key",
        headers={"Authorization": "Bearer anything"},
        json={"api_key": "sk-test"},
    )

    assert response.status_code == 503
