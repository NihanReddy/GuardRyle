from __future__ import annotations

from .decision_engine import DecisionEngine
from .models import Decision, GuardrailResult, Policy


class GuardrailMiddleware:
    """V1 middleware adapter that decides when to evaluate input or output text."""

    def __init__(self, policy: Policy | None = None, decision_engine: DecisionEngine | None = None):
        self.policy = policy
        self.decision_engine = decision_engine or DecisionEngine()

    def evaluate(self, text: str, policy: Policy | None = None) -> GuardrailResult:
        resolved_policy = policy or self.policy
        if resolved_policy is None:
            raise ValueError("A policy must be provided to evaluate text.")
        return self.decision_engine.decide(text, resolved_policy)

    def guard_input(self, text: str, policy: Policy | None = None) -> GuardrailResult:
        return self.evaluate(text, policy)

    def guard_output(self, text: str, policy: Policy | None = None) -> GuardrailResult:
        return self.evaluate(text, policy)

    def allow(self, text: str, policy: Policy | None = None) -> bool:
        return self.evaluate(text, policy).decision == Decision.ALLOW
