from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from time import perf_counter
from uuid import uuid4

from .config import RuntimeConfig
from .decision_engine import DecisionEngine
from .models import Decision, GuardrailResult, Policy


REQUIRED_EVALUATION_UNAVAILABLE = "required_evaluation_unavailable"
EVALUATION_UNAVAILABLE = "evaluation_unavailable"


@dataclass(slots=True)
class AuditEvent:
    request_id: str
    decision: Decision
    reason_code: str
    degraded_mode: bool
    provider_used: str | None
    latency_ms: float


class SecurityPipeline:
    """Runs policy evaluation and provides fail-closed operation enforcement."""

    def __init__(
        self,
        decision_engine: DecisionEngine,
        config: RuntimeConfig | None = None,
        audit_sink: Callable[[AuditEvent], None] | None = None,
    ):
        self.decision_engine = decision_engine
        self.config = config or RuntimeConfig()
        self.audit_events: list[AuditEvent] = []
        self.audit_sink = audit_sink

    def evaluate(
        self,
        text: str,
        policy: Policy,
        *,
        required_semantic_check: bool = False,
        provider_used: str | None = None,
    ) -> GuardrailResult:
        request_id = str(uuid4())
        started = perf_counter()
        try:
            result = self.decision_engine.decide(text, policy)
        except (RuntimeError, ValueError, TimeoutError):
            failure_reason = (
                REQUIRED_EVALUATION_UNAVAILABLE
                if required_semantic_check
                else EVALUATION_UNAVAILABLE
            )
            result = GuardrailResult(
                decision=Decision.DENY,
                reasons=["Security evaluation could not be completed."],
                metadata={
                    "degraded_mode": True,
                    "required_check_failed": True,
                    "failure_reason": failure_reason,
                },
            )

        latency_ms = (perf_counter() - started) * 1000
        degraded = bool(result.metadata.get("degraded_mode", False))
        result.metadata.update({
            "request_id": request_id,
            "provider_used": provider_used,
            "degraded_mode": degraded,
            "latency_ms": latency_ms,
        })
        event = AuditEvent(
            request_id, result.decision,
            (
                result.metadata.get("failure_reason")
                if result.metadata.get("required_check_failed")
                else "degraded_evaluation" if degraded else f"decision_{result.decision.value}"
            ),
            degraded, provider_used, latency_ms,
        )
        self.audit_events.append(event)
        if self.audit_sink is not None:
            self.audit_sink(event)
        return result

    @staticmethod
    def is_authorized(result: GuardrailResult) -> bool:
        """Return whether a result may authorize a protected operation."""
        return result.authorized

    def enforce(self, result: GuardrailResult) -> GuardrailResult:
        """Block protected operations unless the result explicitly allows them."""
        if not self.is_authorized(result):
            raise PermissionError("Protected operation is not authorized.")
        return result
