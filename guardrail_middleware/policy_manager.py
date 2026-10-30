from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from threading import RLock
from typing import Any

from .models import Decision, Policy, PolicyRule
from .policy_config import PolicyConfigLoader


class InvalidPolicyError(ValueError):
    """Raised when a policy definition does not satisfy the policy contract."""


class RuleCompilationError(InvalidPolicyError):
    """Raised when a regex rule cannot be compiled."""


class PolicyManager:
    """Thread-safe registry for validated policies and runtime rule changes."""

    def __init__(self, policies: list[Policy] | None = None):
        self._lock = RLock()
        self._policies: dict[str, Policy] = {}
        for policy in policies or []:
            self.register(policy)

    def load(self, source: dict[str, Any] | list[dict[str, Any]] | str | Path) -> list[Policy]:
        """Load, validate, and register policies from a mapping or JSON/YAML file."""
        if isinstance(source, dict):
            policies = [self._policy_from_definition(source)]
        elif isinstance(source, list):
            policies = [self._policy_from_definition(definition) for definition in source]
        else:
            try:
                policies = [self.validate(policy) for policy in PolicyConfigLoader.load_file(source)]
            except (OSError, ImportError, json.JSONDecodeError, TypeError, ValueError) as error:
                if isinstance(error, InvalidPolicyError):
                    raise
                raise InvalidPolicyError(f"Unable to load policy file: {error}") from error

        with self._lock:
            ids = [policy.id for policy in policies]
            if len(ids) != len(set(ids)) or any(policy_id in self._policies for policy_id in ids):
                raise InvalidPolicyError("Policy IDs must be unique.")
            self._policies.update(copy.deepcopy({policy.id: policy for policy in policies}))
        return copy.deepcopy(policies)

    def register(self, policy: Policy | dict[str, Any]) -> Policy:
        """Atomically add a new policy, rejecting an existing policy ID."""
        validated = self._coerce_policy(policy)
        with self._lock:
            if validated.id in self._policies:
                raise InvalidPolicyError(f"Policy ID already exists: {validated.id!r}")
            self._policies[validated.id] = copy.deepcopy(validated)
        return copy.deepcopy(validated)

    def get(self, policy_id: str) -> Policy:
        """Return a defensive copy of an active policy."""
        with self._lock:
            try:
                return copy.deepcopy(self._policies[policy_id])
            except KeyError as error:
                raise KeyError(f"Unknown policy ID: {policy_id!r}") from error

    def list(self) -> list[Policy]:
        """Return defensive copies of all active policies."""
        with self._lock:
            return copy.deepcopy(list(self._policies.values()))

    def update_rule(self, policy_id: str, rule: PolicyRule | dict[str, Any]) -> Policy:
        """Add or replace a rule by ID and atomically publish the updated policy."""
        return self._set_rule(policy_id, rule)

    def add_rule(self, policy_id: str, rule: PolicyRule | dict[str, Any]) -> Policy:
        """Add a rule and reject the operation if its ID is already registered."""
        new_rule = self._coerce_rule(rule)
        with self._lock:
            policy = self.get(policy_id)
            if any(existing.id == new_rule.id for existing in policy.rules):
                raise InvalidPolicyError(f"Rule ID already exists: {new_rule.id!r}")
            policy.rules.append(new_rule)
            self.validate(policy)
            self._policies[policy_id] = copy.deepcopy(policy)
            return copy.deepcopy(policy)

    def _set_rule(self, policy_id: str, rule: PolicyRule | dict[str, Any]) -> Policy:
        new_rule = self._coerce_rule(rule)
        with self._lock:
            policy = self.get(policy_id)
            policy.rules = [existing for existing in policy.rules if existing.id != new_rule.id]
            policy.rules.append(new_rule)
            self.validate(policy)
            self._policies[policy_id] = copy.deepcopy(policy)
            return copy.deepcopy(policy)

    def disable_rule(self, policy_id: str, rule_id: str) -> Policy:
        """Disable a rule without removing it from the policy."""
        with self._lock:
            policy = self.get(policy_id)
            for rule in policy.rules:
                if rule.id == rule_id:
                    rule.enabled = False
                    self._policies[policy_id] = copy.deepcopy(policy)
                    return copy.deepcopy(policy)
        raise KeyError(f"Unknown rule ID: {rule_id!r}")

    @classmethod
    def validate(cls, policy: Policy) -> Policy:
        """Validate a model and return it for convenient use in callers."""
        if not policy.id.strip():
            raise InvalidPolicyError("Policy ID must not be empty.")
        if policy.default_decision not in set(Decision):
            raise InvalidPolicyError("Default decision must be ALLOW, DENY, or REVIEW.")
        rule_ids = [rule.id for rule in policy.rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise InvalidPolicyError("Rule IDs must be unique within a policy.")
        for rule in policy.rules:
            cls._validate_rule(rule)
        for name in ("semantic_deny_threshold", "semantic_review_threshold", "fuzzy_threshold"):
            value = getattr(policy, name)
            if value is not None and not 0.0 <= value <= 1.0:
                raise InvalidPolicyError(f"{name} must be between 0.0 and 1.0.")
        if policy.semantic_top_k < 1:
            raise InvalidPolicyError("semantic_top_k must be at least 1.")
        return policy

    @classmethod
    def _validate_rule(cls, rule: PolicyRule) -> None:
        if not rule.id.strip():
            raise InvalidPolicyError("Rule IDs must not be empty.")
        if rule.decision not in set(Decision):
            raise InvalidPolicyError(f"Invalid decision for rule {rule.id!r}.")
        if rule.match_type not in {"exact", "regex", "fuzzy"}:
            raise InvalidPolicyError(f"Unsupported match type: {rule.match_type!r}")
        if rule.match_type == "regex":
            try:
                re.compile(rule.value)
            except re.error as error:
                raise RuleCompilationError(f"Invalid regex for rule {rule.id!r}: {error}") from error

    @classmethod
    def _policy_from_definition(cls, definition: dict[str, Any]) -> Policy:
        if not isinstance(definition, dict):
            raise InvalidPolicyError("Each policy definition must be a dictionary.")
        cls._validate_definition_thresholds(definition)
        try:
            policy = PolicyConfigLoader.from_dict(definition)
        except (TypeError, ValueError) as error:
            raise InvalidPolicyError(str(error)) from error
        return cls.validate(policy)

    @classmethod
    def _coerce_policy(cls, policy: Policy | dict[str, Any]) -> Policy:
        if isinstance(policy, Policy):
            return cls.validate(copy.deepcopy(policy))
        return cls._policy_from_definition(policy)

    @classmethod
    def _coerce_rule(cls, rule: PolicyRule | dict[str, Any]) -> PolicyRule:
        try:
            parsed = rule if isinstance(rule, PolicyRule) else PolicyConfigLoader._rule_from_dict(rule)
        except (TypeError, ValueError) as error:
            raise InvalidPolicyError(str(error)) from error
        cls._validate_rule(parsed)
        return copy.deepcopy(parsed)

    @staticmethod
    def _validate_definition_thresholds(definition: dict[str, Any]) -> None:
        for name in ("fuzzy_threshold", "semantic_similarity_threshold", "semantic_deny_threshold", "semantic_review_threshold"):
            if name in definition and definition[name] is not None:
                try:
                    value = float(definition[name])
                except (TypeError, ValueError) as error:
                    raise InvalidPolicyError(f"{name} must be numeric.") from error
                if not 0.0 <= value <= 1.0:
                    raise InvalidPolicyError(f"{name} must be between 0.0 and 1.0.")
        top_k = definition.get("semantic_top_k", definition.get("top_k"))
        if top_k is not None and (not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1):
            raise InvalidPolicyError("semantic_top_k must be a positive integer.")