from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class EvaluationExample:
    id: str
    text: str
    category: str
    policy: str = "general"
    expected_decision: str = "allow"
    metadata: dict[str, Any] = field(default_factory=dict)
    label: str | None = None

    def __post_init__(self) -> None:
        if self.label is not None:
            self.expected_decision = self._decision_from_label(self.label)
        self.expected_decision = self.expected_decision.strip().lower()
        if self.expected_decision not in {"allow", "review", "deny"}:
            raise ValueError(f"Unsupported expected decision: {self.expected_decision!r}")

    @staticmethod
    def _decision_from_label(label: str) -> str:
        normalized = label.strip().lower()
        if normalized == "safe":
            return "allow"
        if normalized == "ambiguous":
            return "review"
        if normalized == "unsafe":
            return "deny"
        return normalized

    @property
    def compatible_label(self) -> str:
        """Return the legacy dataset label for callers that still need it."""
        return {
            "allow": "safe",
            "review": "ambiguous",
            "deny": "unsafe",
        }[self.expected_decision]


@dataclass(slots=True)
class EvaluationDataset:
    examples: list[EvaluationExample]

    @classmethod
    def from_json(cls, payload: str | dict[str, Any]) -> "EvaluationDataset":
        if isinstance(payload, str):
            raw = json.loads(payload)
        elif isinstance(payload, dict):
            raw = payload
        else:
            raise TypeError("Dataset payload must be a JSON string or dictionary.")

        examples = raw.get("examples", [])
        return cls([EvaluationExample(**example) for example in examples])

    @classmethod
    def from_file(cls, path: str | Path) -> "EvaluationDataset":
        with Path(path).open("r", encoding="utf-8") as handle:
            return cls.from_json(json.load(handle))

    def filter_by_category(self, category: str) -> list[EvaluationExample]:
        return [example for example in self.examples if example.category == category]

    def summary(self) -> dict[str, int]:
        return dict(Counter(example.compatible_label for example in self.examples))

    def decision_summary(self) -> dict[str, int]:
        return dict(Counter(example.expected_decision for example in self.examples))

    def category_summary(self) -> dict[str, int]:
        return dict(Counter(example.category for example in self.examples))
