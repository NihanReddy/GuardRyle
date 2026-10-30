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

## Launch the backend and frontend

Install the package, including the FastAPI adapter:

```bash
python -m pip install -e .
```

Configure the administrative API and CORS allowlist in the server environment.
Do not commit these values:

```bash
# Required for PUT/POST configuration endpoints.
set GUARDRYLE_ADMIN_TOKEN=replace-with-a-long-random-token
# Comma-separated exact browser origins; do not use '*' with credentials.
set GUARDRYLE_CORS_ORIGINS=http://localhost:5173
# Optional server-side OpenAI credential. PUT /api/providers/openai/key
# stores a replacement only in the running server process.
set OPENAI_API_KEY=replace-with-secret
# Optional model used by the OpenAI connection test.
set OPENAI_EMBEDDING_MODEL=your-configured-embedding-model
```

Start the API from the repository root:

```bash
python -m uvicorn guardrail_middleware.api:app --reload
```

The default application registers GuardRyle's local
`sentence-transformers/all-MiniLM-L6-v2` provider with 384 dimensions and local
execution. A hosting application that passes a custom registry through
`create_app(...)` replaces this default for production provider composition.
The adapter never claims a remote model or device that was not initialized.
The administrative endpoints require `Authorization: Bearer
<GUARDRYLE_ADMIN_TOKEN>` and return sanitized errors.

The React dashboard lives in `front-end/` and provides a live control-room
view for blocked requests, review queues, active policy health, provider
status, latency, and request-volume trends. It reads sanitized runtime audit
events from the backend operational store, so the operations view is not based
on representative data.

Start the Vite development server:

```bash
cd front-end
npm install
npm run dev
```

Open the local URL printed by Vite, normally `http://localhost:5173/`.
During Vite development, `/api` requests are proxied to
`http://127.0.0.1:8000`; start both processes to use live runtime settings.

The dashboard includes:

- Blocked, review, allowed, degraded, and reviewed runtime metric cards
- Live decision-distribution charts and average latency
- Recent sanitized runtime event log with persistent review state
- JSON/YAML policy upload controls with validation-ready feedback
- Policy health and version coverage panel
- Responsive desktop, tablet, and narrow-screen layouts
- A Settings panel for live embedding-provider/model status and OpenAI configuration

### Runtime provider settings

The existing Settings control opens the Runtime providers & security panel on the
overview page. It reads these same-origin backend endpoints when the application
is deployed with an API server:

- `GET /api/embedding/status` reports the configured primary model and the model
  actually used for the latest request, including provider, dimensions,
  local/remote execution, health, and degraded mode.
- `GET /api/embedding/providers` reports provider capabilities and supported
  dimensions.
- `PUT /api/embedding/config` changes provider/model selection only after the
  backend accepts it.
- `GET /api/providers/openai/status`, `PUT /api/providers/openai/key`, and
  `POST /api/providers/openai/test` support masked OpenAI configuration and
  backend-confirmed connection testing.
- `GET /api/dashboard` returns live runtime counts, active policy information,
  latency, and sanitized audit events from the operational store.
- `POST /api/dashboard/events/{request_id}/review` persists review state for a
  runtime event and requires the admin bearer token.
- `POST /api/evaluate` evaluates a request through `SecurityPipeline`, persists
  a sanitized audit event in SQLite, and returns only the decision, safe reason
  codes/hits, request ID, provider, degraded state, and latency. It requires
  the admin bearer token.

`PUT` and `POST` configuration endpoints require the admin bearer token.
`GET` endpoints expose only safe status metadata. `PUT /api/providers/openai/key`
keeps the credential server-side and returns only configured/connection state;
it does not persist to browser storage or return the key. The connection test
performs an actual OpenAI embeddings request (or a host-provided test callback)
and reports success only after a valid embedding response. Failed tests are
sanitized and do not expose provider exceptions.

The adapter validates provider and model identity against the injected
`ProviderRegistry`. It does not change registry health, silently select a
fallback provider, or claim device/GPU information that the provider metadata
does not report. `SecurityPipeline` remains the authority for fail-closed
required checks; the API adapter does not convert `REVIEW` into approval.

Runtime events are stored in `data/guardryle_runtime.sqlite3` by default. Set
`GUARDRYLE_RUNTIME_DB` to use another protected path. The store contains no
prompt text or API keys. Back up and protect this file as operational audit
data; it is not a replacement for a multi-node production event store.

OpenAI credentials are stored through the host OS credential manager using
`keyring` (Windows Credential Manager on Windows), not in configuration files.
If secure credential storage is unavailable, key configuration fails rather
than silently reverting to process-only storage. OpenAI connection checks
validate both the selected model and returned dimensions against the optional
`VectorStore.model_metadata` before reporting success. A missing configured
provider is reported with `configurationValid: false`; it is never presented
as an active provider.

Hosts that execute requests should pass their live `SecurityPipeline` to
`create_app(..., security_pipeline=pipeline)`. Its audit events update the
active provider/model status only when a request supplies `provider_used`.

The frontend does not provide substitute runtime values when these endpoints
are unavailable. It displays an explicit unavailable/error state instead.
Backend implementations must return only `configured: true|false` for OpenAI
credentials; API keys must be held by the server's secret manager or process
environment and must never be returned to the browser, logged, or placed in a
URL. Provider status payloads should use `ProviderRegistry.status()` so
capabilities are visible without exposing credentials.

If a provider fails or a required security evaluation is unavailable, the UI
shows degraded/failure status. GuardRyle's fail-closed behavior denies required
evaluations that cannot complete; the UI never treats `REVIEW` as approval.

## Development checks

Run the test suite with:

```bash
pytest -q
```

The API exposes `/health/live` and `/health/ready` for container probes.
Deployment and service-to-service chat integration instructions are in
[`DEPLOYMENT.md`](./DEPLOYMENT.md). Protected API calls use the configured
server-side token as `Authorization: Bearer <GUARDRYLE_ADMIN_TOKEN>`; never
place that token in a browser bundle.

A Python environment without the optional Hugging Face dependency can still generate datasets using the built-in fallback cases.

## Provider and failure policy

The optional runtime settings in [`guardrail_config.json`](./guardrail_config.json) are
validated by `RuntimeConfig`. Provider credentials are never read from that file; adapters
should obtain them from environment variables or a secret manager. `ProviderRegistry`
selects only explicitly registered healthy providers, and `VectorStore` can enforce model
identity, dimensions, and finite numeric values through `EmbeddingMetadata`.

Use `SecurityPipeline` for operations that require a semantic check. It records request IDs,
latency, provider, degraded mode, and a reason code without storing prompt content. Required
checks return `deny` with the stable `required_evaluation_unavailable` reason code when
unavailable, regardless of the policy default or degraded-mode setting. Callers protecting an
operation should pass the result to `SecurityPipeline.enforce`; only an explicit `allow`
result is authorized. `review` remains available for genuine human-review workflows but never
authorizes an operation.
