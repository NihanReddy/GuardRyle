import math

import pytest

from guardrail_middleware import (
    Decision,
    EmbeddingMetadata,
    GuardrailResult,
    Policy,
    ProviderError,
    ProviderRegistry,
    RuntimeConfig,
    SecurityPipeline,
    VectorCompatibilityError,
    VectorStore,
)


class FakeProvider:
    def __init__(self, model_id: str, dimensions: int):
        self.metadata = EmbeddingMetadata("fake", model_id, dimensions, "local")

    def embed(self, text: str) -> list[float]:
        return [1.0] * self.metadata.dimensions


def test_registry_skips_unhealthy_provider():
    registry = ProviderRegistry()
    registry.register("remote", FakeProvider("remote-v1", 3), healthy=False)
    registry.register("local", FakeProvider("local-v1", 3))

    name, provider = registry.select(["remote", "local"])

    assert name == "local"
    assert provider.metadata.model_id == "local-v1"


def test_registry_reports_no_healthy_provider():
    registry = ProviderRegistry()
    registry.register("remote", FakeProvider("remote-v1", 3), healthy=False)

    with pytest.raises(ProviderError):
        registry.select(["remote"])


def test_registry_status_exposes_capabilities_without_credentials():
    registry = ProviderRegistry()
    registry.register("local", FakeProvider("local-v1", 3))

    assert registry.status() == [{
        "id": "local",
        "health": "healthy",
        "provider": "fake",
        "model_id": "local-v1",
        "dimensions": 3,
        "execution": "local",
    }]


def test_vector_store_rejects_invalid_dimensions_and_values(tmp_path):
    metadata = EmbeddingMetadata("fake", "model-v1", 3, "local")
    store = VectorStore(tmp_path / "vectors.json", model_metadata=metadata)

    with pytest.raises(VectorCompatibilityError):
        store.add_document("wrong-size", "text", vector=[1.0, 2.0])
    with pytest.raises(VectorCompatibilityError):
        store.add_document("nan", "text", vector=[1.0, math.nan, 2.0])


def test_same_dimension_different_model_is_rejected(tmp_path):
    path = tmp_path / "vectors.json"
    first = VectorStore(path, model_metadata=EmbeddingMetadata("fake", "model-v1", 3, "local"))
    first.add_document("one", "text", vector=[1.0, 0.0, 0.0])
    first.persist()

    second = VectorStore(path, model_metadata=EmbeddingMetadata("fake", "model-v2", 3, "local"))
    with pytest.raises(VectorCompatibilityError):
        second.search([1.0, 0.0, 0.0])


def test_security_pipeline_fails_closed_for_required_evaluation():
    class BrokenEngine:
        def decide(self, text: str, policy: Policy):
            raise RuntimeError("provider unavailable")

    pipeline = SecurityPipeline(BrokenEngine())
    result = pipeline.evaluate(
        "sensitive operation",
        Policy(id="p", name="p", default_decision=Decision.ALLOW),
        required_semantic_check=True,
    )

    assert result.decision == Decision.DENY
    assert result.metadata["degraded_mode"] is True
    assert result.metadata["failure_reason"] == "required_evaluation_unavailable"
    assert pipeline.audit_events[0].reason_code == "required_evaluation_unavailable"


@pytest.mark.parametrize("default_decision", [Decision.ALLOW, Decision.REVIEW])
def test_required_evaluator_failure_never_authorizes(default_decision):
    class BrokenEngine:
        def decide(self, text: str, policy: Policy):
            raise RuntimeError("provider internals must not escape")

    pipeline = SecurityPipeline(BrokenEngine())
    result = pipeline.evaluate(
        "sensitive operation",
        Policy(id="p", name="p", default_decision=default_decision),
        required_semantic_check=True,
    )

    assert result.decision == Decision.DENY
    assert pipeline.is_authorized(result) is False
    with pytest.raises(PermissionError):
        pipeline.enforce(result)
    assert "provider internals" not in str(result)


@pytest.mark.parametrize("decision", [Decision.REVIEW, Decision.DENY])
def test_non_allow_results_never_authorize_protected_operations(decision):
    pipeline = SecurityPipeline(object())
    result = GuardrailResult(decision=decision)

    assert pipeline.is_authorized(result) is False
    assert bool(result) is False
    with pytest.raises(PermissionError):
        pipeline.enforce(result)


def test_successful_required_check_allows_when_policy_permits():
    class HealthyEngine:
        def decide(self, text: str, policy: Policy):
            return GuardrailResult(decision=Decision.ALLOW)

    pipeline = SecurityPipeline(HealthyEngine())
    result = pipeline.evaluate(
        "safe operation",
        Policy(id="p", name="p", default_decision=Decision.ALLOW),
        required_semantic_check=True,
    )

    assert result.decision == Decision.ALLOW
    assert pipeline.is_authorized(result) is True
    assert pipeline.enforce(result) is result


def test_ordinary_evaluator_failure_denies_by_default():
    class BrokenEngine:
        def decide(self, text: str, policy: Policy):
            raise RuntimeError("provider internals must not escape")

    pipeline = SecurityPipeline(BrokenEngine())
    result = pipeline.evaluate(
        "operation",
        Policy(id="p", name="p", default_decision=Decision.REVIEW),
    )

    assert result.decision == Decision.DENY
    assert result.metadata["degraded_mode"] is True
    assert result.metadata["failure_reason"] == "evaluation_unavailable"
    assert pipeline.is_authorized(result) is False


def test_ordinary_evaluator_failure_cannot_be_enabled_as_fail_open():
    class BrokenEngine:
        def decide(self, text: str, policy: Policy):
            raise RuntimeError("provider unavailable")

    pipeline = SecurityPipeline(
        BrokenEngine(),
        RuntimeConfig(allow_degraded_guardrail=True),
    )
    result = pipeline.evaluate(
        "operation",
        Policy(id="p", name="p", default_decision=Decision.ALLOW),
    )

    assert result.decision == Decision.DENY
    assert result.authorized is False


def test_runtime_config_validates_json_shape(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"version": 1, "remote_timeout_seconds": 0}', encoding="utf-8")

    with pytest.raises(ValueError):
        RuntimeConfig.load_file(path)
