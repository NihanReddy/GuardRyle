from __future__ import annotations

from .decision_engine import DecisionEngine
from .models import Decision, GuardrailResult, Policy
from .semantic_engine import SemanticEngine
from .stream_buffer import StreamBuffer


class StreamingGuardrailMiddleware:
    """V2-ready middleware that evaluates rolling stream chunks using the same engine stack."""

    def __init__(self, policy: Policy | None = None, decision_engine: DecisionEngine | None = None):
        self.policy = policy
        self.decision_engine = decision_engine or DecisionEngine(rule_engine=None, semantic_engine=SemanticEngine())
        self._stream_buffer = StreamBuffer()

    def evaluate_stream(self, chunks: list[str], policy: Policy | None = None) -> GuardrailResult:
        resolved_policy = policy or self.policy
        if resolved_policy is None:
            raise ValueError("A policy must be provided to evaluate stream chunks.")

        self._stream_buffer.clear()
        combined_text = ""
        for chunk in chunks:
            self._stream_buffer.append(chunk)
            combined_text = self._stream_buffer.build_text()
            result = self.decision_engine.decide(combined_text, resolved_policy)
            if result.decision == Decision.DENY:
                return GuardrailResult(
                    decision=Decision.DENY,
                    reasons=result.reasons,
                    rule_hits=result.rule_hits,
                    metadata={
                        "source": "streaming-middleware",
                        "stream_detected": True,
                        "buffer_text": combined_text,
                    },
                )

        final_result = self.decision_engine.decide(combined_text or "", resolved_policy)
        return GuardrailResult(
            decision=final_result.decision,
            reasons=final_result.reasons,
            rule_hits=final_result.rule_hits,
            metadata={
                "source": "streaming-middleware",
                "stream_detected": final_result.decision in {Decision.DENY, Decision.REVIEW},
                "buffer_text": combined_text,
            },
        )
