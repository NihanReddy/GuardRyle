import asyncio
import pytest

from guardrail_middleware import (
    ChatMessage,
    Decision,
    EmbeddingMetadata,
    GuardedChatClient,
    GuardrailBlockedError,
    GuardrailResult,
    Policy,
    SecurityPipeline,
    SemanticEngine,
    SemanticExample,
)


class FakeEmbeddingProvider:
    metadata = EmbeddingMetadata("fake", "fake-v1", 2, "local")

    def embed(self, text: str) -> list[float]:
        return [1.0, 0.0] if "unsafe" in text else [0.0, 1.0]


def test_semantic_engine_uses_registered_embedding_provider():
    policy = Policy(
        id="p",
        name="p",
        semantic_examples=[
            SemanticExample(id="unsafe", text="unsafe example", decision=Decision.DENY)
        ],
        semantic_deny_threshold=0.8,
        semantic_review_threshold=0.5,
    )

    result = SemanticEngine(FakeEmbeddingProvider()).evaluate("unsafe request", policy)

    assert result.decision == Decision.DENY
    assert result.metadata["source"] == "embedding-provider"
    assert result.metadata["model_id"] == "fake-v1"


def test_guarded_chat_client_checks_input_and_output():
    policy = Policy(id="p", name="p", default_decision=Decision.ALLOW, rules=[])
    calls: list[list[ChatMessage]] = []

    async def completion(messages):
        calls.append(list(messages))
        return "safe response"

    class AllowEngine:
        def decide(self, text, policy):
            return GuardrailResult(decision=Decision.ALLOW)

    client = GuardedChatClient(
        completion,
        policy,
        SecurityPipeline(AllowEngine()),
    )

    response = asyncio.run(client.complete([ChatMessage("user", "hello")]))

    assert response.content == "safe response"
    assert len(calls) == 1
    assert response.input_result.decision == Decision.ALLOW
    assert response.output_result.decision == Decision.ALLOW


def test_guarded_chat_client_does_not_call_model_when_input_is_denied():
    policy = Policy(id="p", name="p", default_decision=Decision.DENY, rules=[])
    called = False

    async def completion(messages):
        nonlocal called
        called = True
        return "must not be returned"

    class DenyEngine:
        def decide(self, text, policy):
            return GuardrailResult(decision=Decision.DENY)

    client = GuardedChatClient(completion, policy, SecurityPipeline(DenyEngine()))

    with pytest.raises(GuardrailBlockedError) as error:
        asyncio.run(client.complete([ChatMessage("user", "blocked")]))

    assert error.value.stage == "input"
    assert called is False
