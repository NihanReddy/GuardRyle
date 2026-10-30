from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any


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


@dataclass(slots=True)
class SecurityConfig:
    fail_closed_for_required_checks: bool = True
    require_authorization_for_sensitive_tools: bool = True
    log_sensitive_content: bool = False


@dataclass(slots=True)
class RuntimeConfig:
    """Validated provider and failure-policy settings.

    Credentials are intentionally not represented here; providers read them from
    environment variables or an external secret manager.
    """

    version: int = 1
    allow_degraded_guardrail: bool = False
    alert_on_transformer_failure: bool = True
    primary_provider: str = "local"
    local_fallback_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    preferred_local_model: str | None = None
    provider_selection_mode: str = "configured_priority"
    remote_timeout_seconds: float = 10.0
    max_retries: int = 2
    circuit_breaker_enabled: bool = True
    security: SecurityConfig = field(default_factory=SecurityConfig)

    def __post_init__(self) -> None:
        if self.version != 1:
            raise ValueError("Unsupported guardrail configuration version.")
        if self.provider_selection_mode not in {"configured_priority", "strict"}:
            raise ValueError("provider_selection_mode must be configured_priority or strict.")
        if self.remote_timeout_seconds <= 0:
            raise ValueError("remote_timeout_seconds must be greater than zero.")
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative.")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuntimeConfig":
        security_data = data.get("security", {})
        if not isinstance(security_data, dict):
            raise ValueError("security must be an object.")
        security = SecurityConfig(**security_data)
        values = {key: value for key, value in data.items() if key != "security"}
        return cls(security=security, **values)

    @classmethod
    def load_file(cls, path: str | Path) -> "RuntimeConfig":
        with Path(path).open(encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("Guardrail configuration must be a JSON object.")
        return cls.from_dict(payload)
