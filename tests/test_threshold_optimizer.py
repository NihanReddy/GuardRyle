from guardrail_middleware import Policy, SemanticExample, optimize_thresholds
from guardrail_middleware.threshold_optimizer import format_top_results, iter_search_space, threshold_values


def test_threshold_grid_is_inclusive_and_filters_invalid_combinations():
    assert threshold_values(0.50, 0.90, 0.05) == (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90)
    combinations = list(iter_search_space())

    assert len(combinations) == 198
    assert all(review < deny for deny, review, _ in combinations)


def test_optimizer_returns_ranked_metrics_for_every_configuration():
    policy = Policy(
        id="optimizer-policy",
        name="Optimizer policy",
        semantic_examples=[
            SemanticExample(id="deny-auth", text="bypass authentication", decision="deny"),
            SemanticExample(id="review-account", text="verify account details", decision="review"),
        ],
    )
    dataset = {
        "examples": [
            {"id": "safe", "text": "write a greeting", "expected_decision": "allow", "category": "safe"},
            {"id": "unsafe", "text": "bypass authentication", "expected_decision": "deny", "category": "unsafe"},
        ]
    }

    results = optimize_thresholds(policy, dataset)

    assert len(results) == 198
    assert results[0].f1 >= results[-1].f1
    assert results[0].false_positives >= 0
    assert results[0].false_negatives >= 0
    assert "deny" in format_top_results(results)
    assert "review" in format_top_results(results)