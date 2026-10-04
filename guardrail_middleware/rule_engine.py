from __future__ import annotations

import re
from difflib import SequenceMatcher

from .config import GuardrailConfig
from .engine import GuardrailEngine
from .models import Decision, GuardrailResult, Policy, PolicyRule
from .normalizer import RequestNormalizer


class RuleEngine(GuardrailEngine):
    """Deterministic rule processor for exact, regex, and optional fuzzy rules."""

    def __init__(self, config: GuardrailConfig | None = None):
        self.config = config or GuardrailConfig()

    def evaluate(self, text: str, policy: Policy) -> GuardrailResult:
        normalized_text = RequestNormalizer.normalize(
            text,
            trim=self.config.normalize_whitespace,
            collapse_whitespace=self.config.normalize_whitespace,
        )

        if not normalized_text and not self.config.allow_empty_text:
            return GuardrailResult(
                decision=policy.default_decision,
                reasons=["Input text is empty."],
                rule_hits=[],
                metadata={"source": "rule-engine"},
            )

        decision = policy.default_decision
        reasons: list[str] = []
        rule_hits: list[str] = []

        for rule in policy.rules:
            if not rule.enabled:
                continue

            if self._matches(rule, normalized_text):
                rule_hits.append(rule.id)
                reason = rule.description or f"Matched rule '{rule.id}'"
                reasons.append(reason)

                if rule.decision == Decision.DENY:
                    decision = Decision.DENY
                elif rule.decision == Decision.REVIEW and decision != Decision.DENY:
                    decision = Decision.REVIEW

        if not rule_hits:
            reasons = ["No rules matched the supplied text."] if normalized_text else []

        return GuardrailResult(
            decision=decision,
            reasons=reasons,
            rule_hits=rule_hits[: self.config.max_rule_matches],
            metadata={
                "source": "rule-engine",
                "policy_id": policy.id,
                "matched_rule_count": len(rule_hits),
            },
        )

    def _matches(self, rule: PolicyRule, text: str) -> bool:
        if rule.match_type == "exact":
            return self._match_exact(rule, text)
        if rule.match_type == "regex":
            return self._match_regex(rule, text)
        if rule.match_type == "fuzzy":
            return self._match_fuzzy(rule, text)
        return False

    def _match_exact(self, rule: PolicyRule, text: str) -> bool:
        candidate = rule.value
        comparison_text = text

        if not rule.case_sensitive:
            candidate = candidate.casefold()
            comparison_text = text.casefold()

        return candidate in comparison_text

    def _match_regex(self, rule: PolicyRule, text: str) -> bool:
        flags = 0 if rule.case_sensitive else re.IGNORECASE
        return re.search(rule.value, text, flags) is not None

    def _match_fuzzy(self, rule: PolicyRule, text: str) -> bool:
        if self.config.fuzzy_threshold is None:
            return False

        candidate = rule.value or ""
        if not candidate:
            return False

        score = SequenceMatcher(None, text.casefold(), candidate.casefold()).ratio()
        return score >= self.config.fuzzy_threshold
