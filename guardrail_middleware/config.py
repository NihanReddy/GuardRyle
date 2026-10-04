from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class GuardrailConfig:
    """Configuration for the deterministic rule processing layer."""

    enabled: bool = True
    allow_empty_text: bool = True
    default_policy_id: str | None = None
    fuzzy_threshold: float | None = None
    max_rule_matches: int = 10
    normalize_whitespace: bool = True
    case_sensitive: bool = False
    policy_ids: list[str] = field(default_factory=list)
