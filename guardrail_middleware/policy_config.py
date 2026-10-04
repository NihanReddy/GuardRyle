from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Decision, Policy, PolicyRule, SemanticExample


class PolicyConfigLoader:
    """Loads JSON policy configuration into the in-memory policy model."""

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Policy:
        if not isinstance(data, dict):
            raise TypeError("Policy configuration must be a dictionary.")

        rules = [PolicyConfigLoader._rule_from_dict(rule) for rule in data.get("rules", [])]
        semantic_examples = [
            PolicyConfigLoader._semantic_example_from_dict(example)
            for example in data.get("semantic_examples", [])
        ]

        default_decision = PolicyConfigLoader._parse_decision(
            data.get("default_decision", data.get("action", "allow"))
        )

        return Policy(
            id=str(data.get("id") or data.get("policy_id") or "policy"),
            name=str(data.get("name") or data.get("id") or "Policy"),
            default_decision=default_decision,
            description=str(data.get("description", "")),
            category=str(data.get("category", "general")),
            enabled=bool(data.get("enabled", True)),
            direction=str(data.get("direction", "both")),
            rules=rules,
            semantic_examples=semantic_examples,
            semantic_deny_threshold=float(data.get("semantic_deny_threshold", 0.75)),
            semantic_review_threshold=float(data.get("semantic_review_threshold", 0.55)),
            semantic_top_k=int(data.get("semantic_top_k", 3)),
        )

    @staticmethod
    def load_file(path: str | Path) -> list[Policy]:
        policy_path = Path(path)
        with policy_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        if isinstance(payload, list):
            return [PolicyConfigLoader.from_dict(item) for item in payload]
        if isinstance(payload, dict):
            return [PolicyConfigLoader.from_dict(payload)]
        raise TypeError("Policy configuration file must contain a dictionary or list of dictionaries.")

    @staticmethod
    def load_json(data: str) -> list[Policy]:
        payload = json.loads(data)
        if isinstance(payload, list):
            return [PolicyConfigLoader.from_dict(item) for item in payload]
        return [PolicyConfigLoader.from_dict(payload)]

    @staticmethod
    def _rule_from_dict(data: dict[str, Any]) -> PolicyRule:
        return PolicyRule(
            id=str(data.get("id") or "rule"),
            match_type=str(data.get("match_type", "exact")),
            value=str(data.get("value", "")),
            decision=PolicyConfigLoader._parse_decision(data.get("decision", "deny")),
            description=str(data.get("description", "")),
            case_sensitive=bool(data.get("case_sensitive", False)),
            enabled=bool(data.get("enabled", True)),
        )

    @staticmethod
    def _semantic_example_from_dict(data: dict[str, Any]) -> SemanticExample:
        return SemanticExample(
            id=str(data.get("id") or "semantic-example"),
            text=str(data.get("text", "")),
            decision=PolicyConfigLoader._parse_decision(data.get("decision", "deny")),
            description=str(data.get("description", "")),
            metadata=dict(data.get("metadata", {})),
        )

    @staticmethod
    def _parse_decision(value: Any) -> Decision:
        if isinstance(value, Decision):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"allow", "allowed"}:
                return Decision.ALLOW
            if normalized in {"deny", "denied"}:
                return Decision.DENY
            if normalized in {"review", "reviewed"}:
                return Decision.REVIEW
        raise ValueError(f"Unsupported decision value: {value!r}")
