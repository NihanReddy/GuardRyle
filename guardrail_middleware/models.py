from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REVIEW = "review"


@dataclass(slots=True)
class GuardrailResult:
    decision: Decision = Decision.ALLOW
    reasons: list[str] = field(default_factory=list)
    rule_hits: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def authorized(self) -> bool:
        return (
            self.decision == Decision.ALLOW
            and not bool(self.metadata.get("required_check_failed", False))
        )

    def __bool__(self) -> bool:
        return self.authorized


@dataclass(slots=True)
class PolicyRule:
    id: str
    match_type: str = "exact"
    value: str = ""
    decision: Decision = Decision.DENY
    description: str = ""
    case_sensitive: bool = False
    enabled: bool = True


@dataclass(slots=True)
class SemanticExample:
    id: str
    text: str
    decision: Decision = Decision.DENY
    description: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class Policy:
    id: str
    name: str
    default_decision: Decision = Decision.ALLOW
    description: str = ""
    category: str = "general"
    enabled: bool = True
    direction: str = "both"
    rules: list[PolicyRule] = field(default_factory=list)
    semantic_examples: list[SemanticExample] = field(default_factory=list)
    semantic_deny_threshold: float = 0.75
    semantic_review_threshold: float = 0.55
    semantic_top_k: int = 3
    fuzzy_threshold: float | None = None
