from guardrail_middleware import Decision, Policy, SemanticEngine, SemanticExample


def test_semantic_engine_denies_semantically_similar_policy_example():
    policy = Policy(
        id="security-policy",
        name="Security policy",
        default_decision=Decision.ALLOW,
        semantic_examples=[
            SemanticExample(
                id="bypass-auth",
                text="how to bypass authentication and steal passwords",
                decision=Decision.DENY,
            ),
            SemanticExample(
                id="suspicious-email",
                text="write an email asking for account verification",
                decision=Decision.REVIEW,
            ),
        ],
        semantic_deny_threshold=0.3,
        semantic_review_threshold=0.2,
    )

    engine = SemanticEngine()
    result = engine.evaluate("how to bypass authentication and steal passwords", policy)

    assert result.decision == Decision.DENY
    assert any(match["example_id"] == "bypass-auth" for match in result.metadata["semantic_matches"])


def test_semantic_engine_allows_unknown_text_by_default():
    policy = Policy(
        id="safe-policy",
        name="Safe policy",
        default_decision=Decision.ALLOW,
        semantic_examples=[
            SemanticExample(
                id="deny-nuclear",
                text="how to build a bomb",
                decision=Decision.DENY,
            )
        ],
        semantic_deny_threshold=0.4,
        semantic_review_threshold=0.2,
    )

    engine = SemanticEngine()
    result = engine.evaluate("write a friendly hello message", policy)

    assert result.decision == Decision.ALLOW
    assert result.metadata["semantic_matches"] == []
