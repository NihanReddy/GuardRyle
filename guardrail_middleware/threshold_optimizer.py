from __future__ import annotations

import argparse
import itertools
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .dataset import EvaluationDataset
from .evaluator import EvaluationReport, GuardrailEvaluator
from .models import Policy
from .policy_config import PolicyConfigLoader


@dataclass(frozen=True, slots=True)
class ThresholdResult:
    """Metrics produced for one threshold/top-k configuration."""

    semantic_deny_threshold: float
    semantic_review_threshold: float
    semantic_top_k: int
    precision: float
    recall: float
    f1: float
    false_positives: int
    false_negatives: int

    @classmethod
    def from_report(
        cls,
        deny_threshold: float,
        review_threshold: float,
        top_k: int,
        report: EvaluationReport,
    ) -> "ThresholdResult":
        return cls(
            semantic_deny_threshold=deny_threshold,
            semantic_review_threshold=review_threshold,
            semantic_top_k=top_k,
            precision=report.precision,
            recall=report.recall,
            f1=report.f1,
            false_positives=report.false_positives,
            false_negatives=report.false_negatives,
        )


def threshold_values(start: float, stop: float, step: float) -> tuple[float, ...]:
    """Return an inclusive, rounded decimal grid without floating-point drift."""
    count = round((stop - start) / step)
    return tuple(round(start + index * step, 2) for index in range(count + 1))


def iter_search_space(
    deny_thresholds: Iterable[float] | None = None,
    review_thresholds: Iterable[float] | None = None,
    top_ks: Iterable[int] = (1, 2, 3),
) -> Iterable[tuple[float, float, int]]:
    """Yield only configurations where review threshold is below deny threshold."""
    deny_values = deny_thresholds or threshold_values(0.50, 0.90, 0.05)
    review_values = review_thresholds or threshold_values(0.30, 0.70, 0.05)
    return (
        (deny, review, top_k)
        for deny, review, top_k in itertools.product(deny_values, review_values, top_ks)
        if review < deny
    )


def optimize_thresholds(
    policy: Policy,
    dataset: EvaluationDataset | dict,
) -> list[ThresholdResult]:
    """Evaluate every valid search configuration and return results best-first."""
    results: list[ThresholdResult] = []
    for deny_threshold, review_threshold, top_k in iter_search_space():
        candidate = Policy(
            id=policy.id,
            name=policy.name,
            default_decision=policy.default_decision,
            description=policy.description,
            category=policy.category,
            enabled=policy.enabled,
            direction=policy.direction,
            rules=policy.rules,
            semantic_examples=policy.semantic_examples,
            semantic_deny_threshold=deny_threshold,
            semantic_review_threshold=review_threshold,
            semantic_top_k=top_k,
            fuzzy_threshold=policy.fuzzy_threshold,
        )
        report = GuardrailEvaluator(policy=candidate).evaluate_dataset(dataset)
        results.append(ThresholdResult.from_report(deny_threshold, review_threshold, top_k, report))

    return sorted(
        results,
        key=lambda result: (
            result.f1,
            result.recall,
            result.precision,
            -result.false_positives,
            -result.false_negatives,
        ),
        reverse=True,
    )


def format_top_results(results: list[ThresholdResult], limit: int = 5) -> str:
    """Format the highest-scoring configurations as a compact text table."""
    headers = ("deny", "review", "top_k", "precision", "recall", "f1", "FP", "FN")
    rows = [
        (
            f"{result.semantic_deny_threshold:.2f}",
            f"{result.semantic_review_threshold:.2f}",
            str(result.semantic_top_k),
            f"{result.precision:.4f}",
            f"{result.recall:.4f}",
            f"{result.f1:.4f}",
            str(result.false_positives),
            str(result.false_negatives),
        )
        for result in results[:limit]
    ]
    widths = [max(len(header), *(len(row[index]) for row in rows)) for index, header in enumerate(headers)]
    lines = ["  ".join(header.ljust(widths[index]) for index, header in enumerate(headers))]
    lines.append("  ".join("-" * width for width in widths))
    lines.extend("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)) for row in rows)
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Optimize GuardRyle semantic policy thresholds.")
    parser.add_argument("--policy", required=True, type=Path, help="JSON/YAML policy file to optimize.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/representative_dataset.json"),
        help="Evaluation dataset JSON file (default: data/representative_dataset.json).",
    )
    parser.add_argument("--top", type=int, default=5, help="Number of configurations to print (default: 5).")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    policies = PolicyConfigLoader.load_file(args.policy)
    if len(policies) != 1:
        raise ValueError("The optimizer requires a policy file containing exactly one policy.")

    dataset = EvaluationDataset.from_file(args.dataset)
    results = optimize_thresholds(policies[0], dataset)
    best = results[0]
    print(f"Evaluated {len(results)} valid configurations across {len(dataset.examples)} examples.")
    print(format_top_results(results, args.top))
    print("\nOptimal policy configuration:")
    print(f"semantic_deny_threshold: {best.semantic_deny_threshold:.2f}")
    print(f"semantic_review_threshold: {best.semantic_review_threshold:.2f}")
    print(f"semantic_top_k: {best.semantic_top_k}")


if __name__ == "__main__":
    main()