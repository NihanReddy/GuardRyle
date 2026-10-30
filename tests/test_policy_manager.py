import json

import pytest

from guardrail_middleware import Decision, InvalidPolicyError, PolicyManager, RuleCompilationError


def policy_data() -> dict:
    return {
        "id": "policy-1",
        "name": "Test policy",
        "default_decision": "allow",
        "fuzzy_threshold": 0.7,
        "semantic_deny_threshold": 0.8,
        "semantic_review_threshold": 0.5,
        "semantic_top_k": 2,
        "rules": [{"id": "deny-secret", "match_type": "exact", "value": "secret"}],
    }


def test_manager_loads_and_validates_json_file(tmp_path):
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy_data()), encoding="utf-8")

    manager = PolicyManager()
    loaded = manager.load(path)

    assert loaded[0].id == "policy-1"
    assert manager.get("policy-1").fuzzy_threshold == 0.7


def test_manager_loads_yaml_file(tmp_path):
    path = tmp_path / "policy.yaml"
    path.write_text("id: yaml-policy\nname: YAML\ndefault_decision: DENY\nrules: []\n", encoding="utf-8")

    policy = PolicyManager().load(path)[0]

    assert policy.default_decision == Decision.DENY


def test_manager_rejects_malformed_regex():
    data = policy_data()
    data["rules"] = [{"id": "bad", "match_type": "regex", "value": "("}]

    with pytest.raises(RuleCompilationError):
        PolicyManager().load(data)


def test_manager_rejects_duplicate_rule_ids_and_invalid_thresholds():
    data = policy_data()
    data["rules"] = [{"id": "same"}, {"id": "same"}]
    with pytest.raises(InvalidPolicyError, match="unique"):
        PolicyManager().load(data)

    data = policy_data()
    data["semantic_deny_threshold"] = 1.1
    with pytest.raises(InvalidPolicyError, match="between"):
        PolicyManager().load(data)


def test_manager_updates_and_disables_rules_atomically():
    manager = PolicyManager()
    manager.load(policy_data())

    updated = manager.update_rule("policy-1", {"id": "deny-secret", "value": "password"})
    assert updated.rules[0].value == "password"
    assert manager.get("policy-1").rules[0].enabled is True

    disabled = manager.disable_rule("policy-1", "deny-secret")
    assert disabled.rules[0].enabled is False


def test_manager_adds_new_rule_and_rejects_duplicate_rule_id():
    manager = PolicyManager()
    manager.load(policy_data())

    manager.add_rule("policy-1", {"id": "review-account", "decision": "review"})

    with pytest.raises(InvalidPolicyError, match="already exists"):
        manager.add_rule("policy-1", {"id": "review-account"})