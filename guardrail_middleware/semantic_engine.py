from __future__ import annotations

import math
import re
from collections import Counter

from .engine import GuardrailEngine
from .models import Decision, GuardrailResult, Policy
from .normalizer import RequestNormalizer

_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9]+")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "if",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "our",
    "out",
    "so",
    "that",
    "the",
    "their",
    "them",
    "they",
    "this",
    "those",
    "to",
    "up",
    "we",
    "what",
    "when",
    "where",
    "why",
    "with",
    "you",
    "your",
}


class SemanticEngine(GuardrailEngine):
    """In-memory semantic policy evaluator using deterministic bag-of-words similarity."""

    def evaluate(self, text: str, policy: Policy) -> GuardrailResult:
        normalized_text = RequestNormalizer.normalize(text)

        if not policy.semantic_examples:
            return GuardrailResult(
                decision=policy.default_decision,
                reasons=["No semantic policy examples configured."],
                rule_hits=[],
                metadata={"source": "semantic-engine", "semantic_matches": []},
            )

        if not normalized_text:
            return GuardrailResult(
                decision=policy.default_decision,
                reasons=["Input text is empty."],
                rule_hits=[],
                metadata={"source": "semantic-engine", "semantic_matches": []},
            )

        query_vector = self._vectorize(normalized_text)
        matches = []
        min_semantic_threshold = min(policy.semantic_review_threshold, policy.semantic_deny_threshold)

        for example in policy.semantic_examples:
            example_vector = self._vectorize(example.text)
            score = self._cosine_similarity(query_vector, example_vector)
            if score >= min_semantic_threshold:
                matches.append(
                    {
                        "example_id": example.id,
                        "decision": example.decision,
                        "score": round(score, 4),
                        "text": example.text,
                    }
                )

        matches.sort(key=lambda item: item["score"], reverse=True)
        top_matches = matches[: max(1, policy.semantic_top_k)]

        decision = policy.default_decision
        rule_hits: list[str] = []
        reasons: list[str] = []

        for match in top_matches:
            score = match["score"]
            example_decision = match["decision"]
            if example_decision == Decision.DENY and score >= policy.semantic_deny_threshold:
                decision = Decision.DENY
                rule_hits.append(match["example_id"])
                reasons.append(
                    f"Semantic policy example '{match['example_id']}' matches with similarity {score} and denies the input."
                )
            elif example_decision == Decision.REVIEW and score >= policy.semantic_review_threshold:
                if decision != Decision.DENY:
                    decision = Decision.REVIEW
                rule_hits.append(match["example_id"])
                reasons.append(
                    f"Semantic policy example '{match['example_id']}' matches with similarity {score} and requires review."
                )

        if not reasons:
            reasons = ["No semantic policy examples crossed the configured similarity thresholds."]

        return GuardrailResult(
            decision=decision,
            reasons=reasons,
            rule_hits=rule_hits,
            metadata={
                "source": "semantic-engine",
                "semantic_matches": top_matches,
                "thresholds": {
                    "deny": policy.semantic_deny_threshold,
                    "review": policy.semantic_review_threshold,
                },
            },
        )

    def _vectorize(self, text: str) -> Counter[str]:
        tokens = _TOKEN_PATTERN.findall(RequestNormalizer.normalize(text).lower())
        filtered_tokens = [token for token in tokens if token not in _STOPWORDS]
        return Counter(filtered_tokens)

    def _cosine_similarity(self, left: Counter[str], right: Counter[str]) -> float:
        if not left or not right:
            return 0.0

        overlap = set(left) & set(right)
        if not overlap:
            return 0.0

        numerator = sum(left[token] * right[token] for token in overlap)
        left_norm = math.sqrt(sum(value * value for value in left.values()))
        right_norm = math.sqrt(sum(value * value for value in right.values()))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return numerator / (left_norm * right_norm)
