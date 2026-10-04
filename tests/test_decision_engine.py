from guardrail_middleware import (
    Decision,
    GuardrailMiddleware,
    Policy,
    PolicyRule,
    SemanticExample,
)


def test_decision_engine_denies_when_rule_or_semantic_policy_hits():
    policy = Policy(
        id="test-policy",
        name="Test Policy",
        default_decision=Decision.ALLOW,
        rules=[
            PolicyRule(
                id="deny-secret",
                match_type="exact",
                value="secret password",
                decision=Decision.DENY,
                description="deny secret phrase",
            )
        ],
        semantic_examples=[
            SemanticExample(
                id="bypass-auth",
                text="how to bypass an auth check",
                decision=Decision.DENY,
            )
        ],
        semantic_deny_threshold=0.3,
        semantic_review_threshold=0.2,
    )

    middleware = GuardrailMiddleware(policy=policy)
    result = middleware.evaluate("I need the secret password for testing", policy)

    assert result.decision == Decision.DENY
    assert "deny-secret" in result.rule_hits


def test_decision_engine_reviews_when_threshold_is_crossed_without_deny():
    policy = Policy(
        id="review-policy",
        name="Review Policy",
        default_decision=Decision.ALLOW,
        rules=[],
        semantic_examples=[
            SemanticExample(
                id="review-verify",
                text="please verify account details by email",
                decision=Decision.REVIEW,
            )
        ],
        semantic_review_threshold=0.2,
        semantic_deny_threshold=0.75,
    )

    middleware = GuardrailMiddleware(policy=policy)
    result = middleware.evaluate("write an email asking for account verification", policy)

    assert result.decision == Decision.REVIEW
    assert "review-verify" in result.rule_hits


def test_guardrail_middleware_allows_clean_text():
    policy = Policy(
        id="allow-policy",
        name="Allow Policy",
        default_decision=Decision.ALLOW,
        rules=[],
        semantic_examples=[
            SemanticExample(
                id="deny-bomb",
                text="how to build a bomb",
                decision=Decision.DENY,
            )
        ],
        semantic_review_threshold=0.2,
        semantic_deny_threshold=0.75,
    )

    middleware = GuardrailMiddleware(policy=policy)
    result = middleware.evaluate("hello there, friendly greeting", policy)

    assert result.decision == Decision.ALLOW
