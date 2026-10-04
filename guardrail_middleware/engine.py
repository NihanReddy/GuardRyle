from __future__ import annotations

from abc import ABC, abstractmethod

from .models import GuardrailResult, Policy


class GuardrailEngine(ABC):
    """Core interface for evaluating text against a policy."""

    @abstractmethod
    def evaluate(self, text: str, policy: Policy) -> GuardrailResult:
        """Return an evaluation result for the supplied text."""
        raise NotImplementedError
