"""Export repository evaluation artifacts for the local GuardRyle dashboard."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "front-end" / "public" / "data" / "dashboard.json"


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _decision_counts(confusion_matrix: dict[str, dict[str, int]]) -> dict[str, int]:
    return {
        "blocked": sum(row["deny"] for row in confusion_matrix.values()),
        "review": sum(row["review"] for row in confusion_matrix.values()),
        "allowed": sum(row["allow"] for row in confusion_matrix.values()),
    }


def build_payload() -> dict[str, Any]:
    policy = _read_json(ROOT / "policy.json")
    dataset = _read_json(ROOT / "data" / "representative_dataset.json")
    report = _read_json(ROOT / "reports" / "rules_vs_semantic_comparison.json")
    strategy = report["strategies"]["rules_plus_semantic"]
    examples = {example["id"]: example for example in dataset["examples"]}

    findings = []
    for kind, cases in (
        ("false_positive", strategy["false_positive_cases"]),
        ("false_negative", strategy["false_negative_cases"]),
    ):
        for case in cases:
            source = examples.get(case["id"], {})
            findings.append(
                {
                    "id": case["id"],
                    "prompt": case["text"],
                    "category": source.get("category", "uncategorized"),
                    "policy": source.get("policy", "general"),
                    "expected": case["expected_decision"],
                    "observed": case["decision"],
                    "kind": kind,
                    "latencyMs": case.get("latency_ms"),
                    "source": "rules_plus_semantic",
                }
            )

    return {
        "source": {
            "policy": "policy.json",
            "dataset": "data/representative_dataset.json",
            "report": "reports/rules_vs_semantic_comparison.json",
        },
        "policy": {
            "id": policy.get("id", "unknown"),
            "name": policy.get("name", policy.get("id", "Policy")),
            "defaultDecision": str(policy.get("default_decision", "allow")).lower(),
            "rules": len(policy.get("rules", [])),
            "semanticExamples": len(policy.get("semantic_examples", [])),
            "semanticDenyThreshold": policy.get("semantic_deny_threshold"),
            "semanticReviewThreshold": policy.get("semantic_review_threshold"),
        },
        "dataset": {
            "size": report["dataset_size"],
            "categoryDistribution": report["category_distribution"],
        },
        "evaluation": {
            "strategy": "rules_plus_semantic",
            "metrics": {
                key: strategy[key]
                for key in ("accuracy", "precision", "recall", "f1", "average_latency_ms", "false_positives", "false_negatives")
            },
            "decisionCounts": _decision_counts(strategy["confusion_matrix"]),
            "confusionMatrix": strategy["confusion_matrix"],
        },
        "findings": findings,
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build_payload(), indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()