from __future__ import annotations

from .config import GuardrailConfig
from .models import Decision, GuardrailResult, Policy
from .rule_engine import RuleEngine
from .semantic_engine import SemanticEngine


class DecisionEngine:
    """Combines rule hits and semantic candidates into a single decision."""

    def __init__(
        self,
        rule_engine: RuleEngine | None = None,
        semantic_engine: SemanticEngine | None = None,
        config: GuardrailConfig | None = None,
    ):
        self.rule_engine = rule_engine or RuleEngine(config)
        self.semantic_engine = semantic_engine or SemanticEngine()

    def decide(self, text: str, policy: Policy) -> GuardrailResult:
        rule_result = self.rule_engine.evaluate(text, policy)
        semantic_result = self.semantic_engine.evaluate(text, policy)

        decision = policy.default_decision
        reasons: list[str] = []
        rule_hits: list[str] = []
        metadata: dict[str, object] = {
            "source": "decision-engine",
            "rule_result": rule_result,
            "semantic_result": semantic_result,
            "policy_id": policy.id,
        }

        if rule_result.decision == Decision.DENY:
            decision = Decision.DENY
            reasons.extend(rule_result.reasons)
            rule_hits.extend(rule_result.rule_hits)
            metadata["denied_by"] = "rule"
        elif semantic_result.decision == Decision.DENY:
            decision = Decision.DENY
            reasons.extend(semantic_result.reasons)
            rule_hits.extend(semantic_result.rule_hits)
            metadata["denied_by"] = "semantic"

        if decision == Decision.ALLOW:
            if rule_result.decision == Decision.REVIEW:
                decision = Decision.REVIEW
                reasons.extend(rule_result.reasons)
                rule_hits.extend(rule_result.rule_hits)
                metadata["reviewed_by"] = "rule"
            elif semantic_result.decision == Decision.REVIEW:
                decision = Decision.REVIEW
                reasons.extend(semantic_result.reasons)
                rule_hits.extend(semantic_result.rule_hits)
                metadata["reviewed_by"] = "semantic"

        if decision == Decision.ALLOW and not reasons:
            reasons = ["No guardrail rule or semantic candidate matched."]

        if not rule_hits:
            rule_hits = list(dict.fromkeys(rule_hits))

        return GuardrailResult(
            decision=decision,
            reasons=reasons,
            rule_hits=rule_hits,
            metadata=metadata,
        )
