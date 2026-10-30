from __future__ import annotations

from collections.abc import Iterable

from .decision_engine import DecisionEngine
from .models import Decision, GuardrailResult, Policy
from .semantic_engine import SemanticEngine
from .stream_buffer import StreamBuffer


class StreamingGuardrailMiddleware:
    """Bounded, per-request rolling stream evaluation."""

    def __init__(
        self,
        policy: Policy | None = None,
        decision_engine: DecisionEngine | None = None,
        *,
        max_chunks: int = 1000,
        max_chars: int = 20_000,
    ):
        if max_chunks < 1 or max_chars < 1:
            raise ValueError("Streaming limits must be positive.")
        self.policy = policy
        self.decision_engine = decision_engine or DecisionEngine(rule_engine=None, semantic_engine=SemanticEngine())
        self.max_chunks = max_chunks
        self.max_chars = max_chars

    def evaluate_stream(
        self,
        chunks: Iterable[str],
        policy: Policy | None = None,
    ) -> GuardrailResult:
        resolved_policy = policy or self.policy
        if resolved_policy is None:
            raise ValueError("A policy must be provided to evaluate stream chunks.")

        stream_buffer = StreamBuffer(max_chunks=self.max_chunks, max_chars=self.max_chars)
        try:
            for chunk in chunks:
                if not isinstance(chunk, str):
                    raise ValueError("Stream chunks must be strings.")
                stream_buffer.append(chunk)
                combined_text = stream_buffer.build_text()
                result = self.decision_engine.decide(combined_text, resolved_policy)
                if result.decision == Decision.DENY:
                    return self._stream_result(result, combined_text, detected=True)
            combined_text = stream_buffer.build_text()
            final_result = self.decision_engine.decide(combined_text, resolved_policy)
        except (RuntimeError, TimeoutError, ValueError):
            return GuardrailResult(
                decision=Decision.DENY,
                reasons=["Streaming security evaluation could not be completed."],
                metadata={
                    "source": "streaming-middleware",
                    "stream_detected": False,
                    "stream_failed": True,
                    "required_check_failed": True,
                },
            )

        return self._stream_result(final_result, combined_text, detected=False)

    @staticmethod
    def _stream_result(
        result: GuardrailResult,
        combined_text: str,
        *,
        detected: bool,
    ) -> GuardrailResult:
        return GuardrailResult(
            decision=result.decision,
            reasons=result.reasons,
            rule_hits=result.rule_hits,
            metadata={
                "source": "streaming-middleware",
                "stream_detected": detected or result.decision in {Decision.DENY, Decision.REVIEW},
                "buffer_chars": len(combined_text),
            },
        )
