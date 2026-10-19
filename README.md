# GuardRyle

GuardRyle is an LLM guardrail middleware and evaluation harness. It combines deterministic rules with optional semantic matching and reports precision, recall, F1, and per-example decisions.

## Generate an evaluation dataset

`load_public_benchmark.py` creates a balanced JSON dataset containing harmful `DENY` cases and safe `ALLOW` controls.

The script tries to load `JailbreakBench/JBB-Behaviors` through Hugging Face. If the `datasets` package is unavailable, the network is unavailable, or the benchmark cannot be read, it uses a built-in diverse fallback set.

Install the optional online loader:

```bash
pip install datasets
```

Generate the default 150 harmful and 150 benign examples:

```bash
python load_public_benchmark.py
```

Use a smaller deterministic sample for local iteration:

```bash
python load_public_benchmark.py --harmful 25 --benign 25 --seed 42
```

Options:

- `--harmful N`: number of `DENY` records; default `150`
- `--benign N`: number of `ALLOW` records; default `150`
- `--seed N`: reproducible sampling seed; default `42`
- `--output PATH`: output path; default `eval_dataset_large.json`

The output has this exact interchange shape:

```json
{
  "dataset": [
    {
      "id": "harmful-0001",
      "text": "...",
      "expected_decision": "DENY",
      "category": "credential_theft"
    }
  ]
}
```

When the requested sample is larger than the available local fallback bank, records are cycled deterministically so local test sizes remain configurable.

## Evaluate the generated file

`EvaluationDataset` accepts both the generated `dataset` format and GuardRyle's legacy `examples` format. Load the file and pass it directly to `GuardrailEvaluator`:

```python
from guardrail_middleware import EvaluationDataset, GuardrailEvaluator, PolicyConfigLoader

policy = PolicyConfigLoader.load_file("policy.json")[0]
dataset = EvaluationDataset.from_file("eval_dataset_large.json")
report = GuardrailEvaluator(policy=policy).evaluate_dataset(dataset)

print(report.as_dict())
```

The generated cases are labels for evaluation. They do not change the policy itself; use `policy.json` or another policy configuration to define the rules and semantic examples under test.

## Development checks

Run the test suite with:

```bash
pytest -q
```

A Python environment without the optional Hugging Face dependency can still generate datasets using the built-in fallback cases.
