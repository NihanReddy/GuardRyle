import json

from guardrail_middleware import Decision, PolicyConfigLoader, Policy, PolicyRule, SemanticExample


def test_policy_config_loader_builds_policy_from_dict():
    data = {
        "id": "POL-001",
        "name": "Restricted Access",
        "category": "restricted",
        "description": "Deny harmful instructions",
        "default_decision": "allow",
        "enabled": True,
        "direction": "both",
        "rules": [
            {
                "id": "deny-secret",
                "match_type": "exact",
                "value": "secret password",
                "decision": "deny",
                "description": "deny secret phrase",
            }
        ],
        "semantic_examples": [
            {
                "id": "bypass-auth",
                "text": "how to bypass authentication",
                "decision": "deny",
            }
        ],
        "semantic_deny_threshold": 0.8,
        "semantic_review_threshold": 0.6,
    }

    policy = PolicyConfigLoader.from_dict(data)

    assert isinstance(policy, Policy)
    assert policy.id == "POL-001"
    assert policy.category == "restricted"
    assert policy.enabled is True
    assert policy.direction == "both"
    assert policy.rules[0].decision == Decision.DENY
    assert policy.semantic_examples[0].decision == Decision.DENY


def test_policy_config_loader_reads_json_file(tmp_path):
    policy_path = tmp_path / "policy.json"
    payload = {
        "id": "POL-002",
        "name": "Review Policy",
        "default_decision": "allow",
        "rules": [],
        "semantic_examples": [
            {"id": "review-account", "text": "verify account details", "decision": "review"}
        ],
    }
    policy_path.write_text(json.dumps(payload), encoding="utf-8")

    policies = PolicyConfigLoader.load_file(policy_path)

    assert len(policies) == 1
    assert policies[0].id == "POL-002"
    assert policies[0].semantic_examples[0].decision == Decision.REVIEW
