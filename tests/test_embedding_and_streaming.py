from guardrail_middleware import (
    Decision,
    EmbeddingModel,
    Policy,
    SemanticExample,
    StreamBuffer,
    StreamingGuardrailMiddleware,
    VectorStore,
)


def test_embedding_model_generates_vector_for_text():
    model = EmbeddingModel()
    vector = model.embed("bypass authentication")

    assert isinstance(vector, list)
    assert len(vector) > 0


def test_vector_store_persists_and_searches_top_k(tmp_path):
    store = VectorStore(storage_path=tmp_path / "vectors.json")
    store.add_document(
        "auth-bypass",
        "how to bypass authentication",
        {"decision": Decision.DENY.value},
    )
    store.add_document(
        "safe-greeting",
        "write a friendly greeting",
        {"decision": Decision.ALLOW.value},
    )
    store.persist()

    query = EmbeddingModel().embed("bypass login checks")
    results = store.search(query, top_k=1)

    assert results[0]["id"] == "auth-bypass"
    assert results[0]["score"] >= 0


def test_streaming_guardrail_middleware_detects_unsafe_chunk():
    policy = Policy(
        id="stream-policy",
        name="Stream policy",
        default_decision=Decision.ALLOW,
        semantic_examples=[
            SemanticExample(
                id="unsafe-auth",
                text="bypass authentication",
                decision=Decision.DENY,
            )
        ],
        semantic_deny_threshold=0.1,
        semantic_review_threshold=0.05,
    )

    middleware = StreamingGuardrailMiddleware(policy=policy)
    result = middleware.evaluate_stream(["hello ", "how to bypass authentication"], policy)

    assert result.decision == Decision.DENY
    assert result.metadata["stream_detected"] is True
    assert "buffer_text" not in result.metadata


def test_streaming_guardrail_middleware_has_isolated_bounded_state():
    policy = Policy(id="p", name="p", default_decision=Decision.ALLOW)
    middleware = StreamingGuardrailMiddleware(policy=policy, max_chunks=2, max_chars=8)

    first = middleware.evaluate_stream(["123456789"])
    second = middleware.evaluate_stream(["ok"])

    assert first.metadata["buffer_chars"] == 8
    assert second.metadata["buffer_chars"] == 2


def test_streaming_guardrail_middleware_fails_closed_for_bad_chunk():
    policy = Policy(id="p", name="p", default_decision=Decision.ALLOW)
    middleware = StreamingGuardrailMiddleware(policy=policy)

    result = middleware.evaluate_stream(["safe", 12])  # type: ignore[list-item]

    assert result.decision == Decision.DENY
    assert result.metadata["stream_failed"] is True
    assert result.authorized is False
