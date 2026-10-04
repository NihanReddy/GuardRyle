from __future__ import annotations

import time
from dataclasses import asdict, dataclass, fields
from typing import Any

from .dataset import EvaluationDataset
from .middleware import GuardrailMiddleware
from .models import Decision, Policy


@dataclass(slots=True)
class EvaluationReport:
    total_examples: int
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float
    average_latency_ms: float
    per_example: list[dict[str, Any]]

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def as_dict(self) -> dict[str, Any]:
        return {field.name: getattr(self, field.name) for field in fields(self)}


class GuardrailEvaluator:
    """Simple evaluation runner for representative guardrail datasets."""

    def __init__(self, policy: Policy | None = None, middleware: GuardrailMiddleware | None = None):
        self.policy = policy
        self.middleware = middleware or GuardrailMiddleware(policy=policy)

    def evaluate_dataset(self, dataset: dict[str, Any] | EvaluationDataset) -> EvaluationReport:
        return self._evaluate_with_policy(dataset, self.policy)

    def compare_strategies(self, dataset: dict[str, Any] | EvaluationDataset) -> dict[str, EvaluationReport]:
        normalized_dataset = dataset if isinstance(dataset, EvaluationDataset) else EvaluationDataset.from_json(dataset)

        rules_only_policy = self._policy_without_semantics() if self.policy is not None else None
        if rules_only_policy is None:
            rules_only_report = self._evaluate_with_policy(normalized_dataset, None)
        else:
            rules_only_report = self._evaluate_with_policy(normalized_dataset, rules_only_policy)

        full_report = self._evaluate_with_policy(normalized_dataset, self.policy)
        return {
            "rules_only": rules_only_report,
            "rules_plus_semantic": full_report,
        }

    def build_comparison_report(self, dataset: dict[str, Any] | EvaluationDataset) -> dict[str, Any]:
        normalized_dataset = dataset if isinstance(dataset, EvaluationDataset) else EvaluationDataset.from_json(dataset)
        comparisons = self.compare_strategies(normalized_dataset)

        strategies_report: dict[str, dict[str, Any]] = {}
        disagreements: list[dict[str, Any]] = []

        for name, report in comparisons.items():
            accuracy = self._safe_divide(
                report.true_positives + report.true_negatives,
                report.total_examples,
            )
            strategies_report[name] = {
                "dataset_size": report.total_examples,
                "precision": report.precision,
                "recall": report.recall,
                "f1": report.f1,
                "accuracy": accuracy,
                "false_positives": report.false_positives,
                "false_negatives": report.false_negatives,
                "average_latency_ms": report.average_latency_ms,
                "true_positives": report.true_positives,
                "true_negatives": report.true_negatives,
                "confusion_matrix": self._build_confusion_matrix(report),
                "false_positive_cases": [
                    example for example in report.per_example
                    if example["expected_decision"] == "allow"
                    and example["decision"] in {"deny", "review"}
                ],
                "false_negative_cases": [
                    example for example in report.per_example
                    if example["expected_decision"] == "deny"
                    and example["decision"] == "allow"
                ],
            }

        rules_only = comparisons["rules_only"]
        rules_plus_semantic = comparisons["rules_plus_semantic"]
        semantic_helped: list[dict[str, Any]] = []
        semantic_hurt: list[dict[str, Any]] = []

        for example in normalized_dataset.examples:
            rule_result = self._evaluate_single_example(example, self._policy_without_semantics())
            semantic_result = self._evaluate_single_example(example, self.policy)
            case = {
                "id": example.id,
                "text": example.text,
                "expected_decision": example.expected_decision,
                "category": example.category,
                "policy": example.policy,
                "rules_only_decision": rule_result,
                "rules_plus_semantic_decision": semantic_result,
            }
            if rule_result != semantic_result:
                disagreements.append(case)
                rules_correct = rule_result == example.expected_decision
                semantic_correct = semantic_result == example.expected_decision
                if not rules_correct and semantic_correct:
                    semantic_helped.append(case)
                elif rules_correct and not semantic_correct:
                    semantic_hurt.append(case)

        return {
            "dataset_size": len(normalized_dataset.examples),
            "category_distribution": normalized_dataset.category_summary(),
            "strategies": strategies_report,
            "disagreements": disagreements,
            "semantic_helped": semantic_helped,
            "semantic_hurt": semantic_hurt,
            "results_by_policy": self._summarize_by_policy(normalized_dataset),
        }

    def _evaluate_single_example(self, example: Any, policy: Policy | None) -> str:
        if policy is None:
            return "allow"
        middleware = GuardrailMiddleware(policy=policy)
        result = middleware.evaluate(example.text, policy)
        return result.decision.value

    def _summarize_by_policy(self, dataset: EvaluationDataset) -> dict[str, dict[str, int]]:
        grouped: dict[str, dict[str, int]] = {}
        for example in dataset.examples:
            bucket = grouped.setdefault(example.policy, {"total": 0})
            bucket["total"] += 1
            expected_decision = example.expected_decision
            bucket[expected_decision] = bucket.get(expected_decision, 0) + 1
        return grouped

    @staticmethod
    def _build_confusion_matrix(report: EvaluationReport) -> dict[str, dict[str, int]]:
        matrix = {
            "deny": {"deny": 0, "review": 0, "allow": 0},
            "review": {"deny": 0, "review": 0, "allow": 0},
            "allow": {"deny": 0, "review": 0, "allow": 0},
        }
        for example in report.per_example:
            expected = example["expected_decision"]
            predicted = example["decision"]
            matrix[expected][predicted] += 1
        return matrix

    def _evaluate_with_policy(
        self,
        dataset: dict[str, Any] | EvaluationDataset,
        policy: Policy | None,
    ) -> EvaluationReport:
        normalized_dataset = dataset if isinstance(dataset, EvaluationDataset) else EvaluationDataset.from_json(dataset)
        middleware = GuardrailMiddleware(policy=policy) if policy is not None else GuardrailMiddleware(policy=self.policy)

        true_positives = 0
        false_positives = 0
        true_negatives = 0
        false_negatives = 0
        total_latency_ms = 0.0
        per_example: list[dict[str, Any]] = []

        for example in normalized_dataset.examples:
            start = time.perf_counter()
            result = middleware.evaluate(example.text, policy)
            latency_ms = (time.perf_counter() - start) * 1000
            total_latency_ms += latency_ms

            label_positive = example.expected_decision == "deny"
            prediction_positive = result.decision in {Decision.DENY, Decision.REVIEW}

            if label_positive and prediction_positive:
                true_positives += 1
            elif label_positive and not prediction_positive:
                false_negatives += 1
            elif not label_positive and prediction_positive:
                false_positives += 1
            else:
                true_negatives += 1

            per_example.append(
                {
                    "id": example.id,
                    "text": example.text,
                    "expected_decision": example.expected_decision,
                    "decision": result.decision.value,
                    "prediction_positive": prediction_positive,
                    "latency_ms": round(latency_ms, 4),
                }
            )

        precision = self._safe_divide(true_positives, true_positives + false_positives)
        recall = self._safe_divide(true_positives, true_positives + false_negatives)
        f1 = self._safe_divide(2 * precision * recall, precision + recall)

        return EvaluationReport(
            total_examples=len(normalized_dataset.examples),
            true_positives=true_positives,
            false_positives=false_positives,
            true_negatives=true_negatives,
            false_negatives=false_negatives,
            precision=precision,
            recall=recall,
            f1=f1,
            average_latency_ms=(total_latency_ms / len(normalized_dataset.examples)) if normalized_dataset.examples else 0.0,
            per_example=per_example,
        )

    def _policy_without_semantics(self) -> Policy | None:
        if self.policy is None:
            return None
        return Policy(
            id=f"{self.policy.id}-rules-only",
            name=f"{self.policy.name} (rules only)",
            default_decision=self.policy.default_decision,
            description=self.policy.description,
            category=self.policy.category,
            enabled=self.policy.enabled,
            direction=self.policy.direction,
            rules=self.policy.rules,
            semantic_examples=[],
            semantic_deny_threshold=self.policy.semantic_deny_threshold,
            semantic_review_threshold=self.policy.semantic_review_threshold,
            semantic_top_k=self.policy.semantic_top_k,
        )

    @staticmethod
    def _safe_divide(numerator: float, denominator: float) -> float:
        if denominator == 0:
            return 0.0
        return numerator / denominator
