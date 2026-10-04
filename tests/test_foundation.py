from guardrail_middleware import (
    Decision,
    GuardrailEngine,
    GuardrailResult,
    Policy,
    PolicyRule,
    RuleEngine,
)


def test_guardrail_result_records_decision_and_hits():
    result = GuardrailResult(
        decision=Decision.DENY,
        reasons=["blocked by policy"],
        rule_hits=["deny-secret"],
        metadata={"source": "request"},
    )

    assert result.decision == Decision.DENY
    assert result.reasons == ["blocked by policy"]
    assert result.rule_hits == ["deny-secret"]
    assert result.metadata["source"] == "request"


def test_rule_engine_evaluates_exact_match_and_review_rules():
    policy = Policy(
        id="demo-policy",
        name="Demo policy",
        default_decision=Decision.ALLOW,
        rules=[
            PolicyRule(
                id="deny-secret",
                match_type="exact",
                value="ignore this",
                decision=Decision.DENY,
                description="deny secret phrase",
            ),
            PolicyRule(
                id="review-suspicious",
                match_type="exact",
                value="review this",
                decision=Decision.REVIEW,
                description="review suspicious phrase",
            ),
        ],
    )

    engine = RuleEngine()

    deny_result = engine.evaluate("Please ignore this request.", policy)
    assert deny_result.decision == Decision.DENY
    assert deny_result.rule_hits == ["deny-secret"]

    review_result = engine.evaluate("Please review this request.", policy)
    assert review_result.decision == Decision.REVIEW
    assert review_result.rule_hits == ["review-suspicious"]


def test_guardrail_engine_interface_requires_implementations():
    class DummyEngine(GuardrailEngine):
        def evaluate(self, text: str, policy: Policy) -> GuardrailResult:
            return GuardrailResult(decision=Decision.ALLOW, reasons=[], rule_hits=[], metadata={})

    engine = DummyEngine()
    result = engine.evaluate("hello", Policy(id="p", name="p", default_decision=Decision.ALLOW, rules=[]))

    assert result.decision == Decision.ALLOW
    assert result.rule_hits == []
