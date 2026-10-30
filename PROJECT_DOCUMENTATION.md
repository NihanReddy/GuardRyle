# GuardRyle

GuardRyle is a Python safety layer for chat and AI applications. It checks
text before it reaches an AI model and checks the model response before it
reaches the user.

It returns one of three decisions:

- **ALLOW**: continue.
- **DENY**: stop.
- **REVIEW**: do not continue automatically; ask a person or another process.

## Why it exists

AI applications can receive unsafe requests and can also produce unsafe
answers. GuardRyle gives the application one place to apply safety rules,
record decisions, and measure how well those rules work.

## Main parts

| Part | Purpose |
|---|---|
| `RuleEngine` | Finds exact, pattern, and fuzzy matches. |
| `SemanticEngine` | Finds meaning-based matches using local or remote embeddings. |
| `DecisionEngine` | Combines all checks into one decision. |
| `SecurityPipeline` | Adds failure handling, request IDs, timing, and audit events. |
| `GuardedChatClient` | Checks chat input and output around an AI call. |
| `ProviderRegistry` | Stores the available embedding providers. |
| `PolicyManager` | Loads and validates policies. |
| `GuardrailEvaluator` | Tests a policy against a labeled dataset. |
| FastAPI adapter | Exposes status, evaluation, and provider endpoints. |
| React dashboard | Shows policy, evaluation, provider, and event information. |

## Normal chat workflow

```text
User message
    |
    v
Check input with GuardRyle
    |
    +-- DENY or REVIEW --> stop or send for review
    |
    +-- ALLOW
          |
          v
       Call the AI model
          |
          v
       Check the AI response
          |
          +-- DENY or REVIEW --> do not show the response
          |
          +-- ALLOW --> return response to the user
```

The application should check both sides. Checking only the user message does
not protect users from an unsafe model response.

## How one check works

1. The application sends text and a policy to GuardRyle.
2. The rule check looks for known words and patterns.
3. The semantic check compares the text with policy examples.
4. The decision engine combines the results.
5. A result is returned with the decision, reasons, matched IDs, and timing.
6. The security pipeline records a safe audit event without storing the prompt.

Decision order:

1. Any `DENY` wins.
2. If there is no deny, `REVIEW` wins.
3. Otherwise, the policy default is used.

## Embedding providers

Embeddings turn text into numbers so GuardRyle can compare meaning.

Supported paths:

- **Local provider**: uses the configured local model.
- **OpenAI provider**: calls the OpenAI Embeddings API.
- **Custom provider**: register an object with `metadata` and `embed(text)`.

The active provider must match the policy/index model and vector size. A
provider failure is treated as a failed check. For required checks, GuardRyle
returns `DENY` instead of silently approving the request.

To use OpenAI embeddings:

```text
OPENAI_API_KEY=<server-side-secret>
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_DIMENSIONS=1536
```

Set this in `guardrail_config.json`:

```json
{
  "version": 1,
  "primary_provider": "openai",
  "security": {
    "fail_closed_for_required_checks": true
  }
}
```

Never put provider keys in browser code.

## Connecting a Python chat app

```python
from guardrail_middleware import (
    ChatMessage,
    GuardedChatClient,
    OpenAIChatCompletion,
)

chat = GuardedChatClient(
    completion=OpenAIChatCompletion(
        api_key=OPENAI_API_KEY,
        model="gpt-4o-mini",
    ),
    policy=policy,
    security_pipeline=security_pipeline,
)

result = await chat.complete([
    ChatMessage(role="user", content=user_message),
])

return result.content
```

`GuardedChatClient` calls the model only after the input is allowed. It returns
the answer only after the output is allowed. `GuardrailBlockedError` is raised
for both denied and review results.

For another language or a separate service, call:

```http
POST /api/evaluate
Authorization: Bearer <server-side-admin-token>
Content-Type: application/json
```

```json
{
  "text": "text to check",
  "required_security_check": true,
  "policy_id": "production-policy-v1"
}
```

## Policies

Policies are JSON or YAML files. A policy contains:

- A policy ID and name
- A default decision
- Rules
- Semantic examples
- Similarity thresholds
- The number of matches to inspect

Example rule:

```json
{
  "id": "deny-secret",
  "match_type": "exact",
  "value": "secret password",
  "decision": "DENY"
}
```

Policies should be tested with safe, unsafe, ambiguous, paraphrased, and
adversarial examples before release.

## Streaming

`StreamingGuardrailMiddleware` checks growing text as response chunks arrive.
It can stop after a deny is found. Each call gets its own buffer, and chunk and
character limits prevent unbounded memory use. Bad chunks and evaluation
failures return `DENY`. A network adapter still needs upstream cancellation and
a clear timeout policy.

## API

Useful endpoints:

| Method | Path | Purpose |
|---|---|---|
| GET | `/health/live` | Confirms the process is running. |
| GET | `/health/ready` | Confirms policy, provider, and admin setup. |
| POST | `/api/evaluate` | Evaluates text. |
| GET | `/api/embedding/status` | Shows configured and active provider status. |
| GET | `/api/embedding/providers` | Lists safe provider details. |
| GET | `/api/dashboard` | Returns live runtime counts, policy data, latency, and recent sanitized events. |
| POST | `/api/dashboard/events/{request_id}/review` | Marks a runtime event reviewed; requires the admin token. |
| PUT | `/api/embedding/config` | Selects a registered provider/model. |

Protected requests require:

```http
Authorization: Bearer <GUARDRYLE_ADMIN_TOKEN>
```

The token belongs on the server only.

## Running locally

Backend:

```bash
python -m pip install -e .
python -m uvicorn guardrail_middleware.api:app --reload
```

Frontend:

```bash
cd front-end
npm install
npm run dev
```

Tests:

```bash
pytest -q
```

## Deploying

Build the container:

```bash
docker build -t guardryle:local .
```

Run a single-instance pilot:

```bash
docker run --rm -p 8000:8000 \
  -e GUARDRYLE_ADMIN_TOKEN=<long-random-secret> \
  -e GUARDRYLE_CORS_ORIGINS=https://dashboard.example.com \
  guardryle:local
```

Use a secret manager for keys. Put the service behind HTTPS or a private
network. SQLite is suitable for a pilot with one instance; use a shared
database before running multiple instances.

See [DEPLOYMENT.md](./DEPLOYMENT.md) for the full deployment checklist.

## Evaluation and quality checks

The evaluation tools compare expected labels with actual decisions. They report:

- Accuracy
- Precision
- Recall
- F1
- False positives
- False negatives
- Average latency
- Per-example decisions

These reports help answer whether a rule or semantic example improves safety
without blocking too much safe content.

## Data and privacy

Runtime audit events store decision details, provider information, reason codes,
request IDs, and latency. They do not store prompt text or API keys.

Protect the runtime database because it is operational data. Do not commit:

- API keys
- `.env` files
- Runtime SQLite files
- Generated Python cache files
- Browser admin tokens

## Current limits

- The dashboard is mainly an operations view, not a complete user-auth system.
- SQLite is not a shared multi-instance event store.
- Streaming needs a production network adapter for upstream cancellation.
- Tool/function-call checks need to be added before allowing sensitive tools.
- Rate limits, shared storage, detailed monitoring, and policy approval workflows
  are still needed for a larger public service.

## Simple operating rule

For normal chat, use `required_security_check=true` when the request can cause
harm, expose private data, change an account, spend money, or call a sensitive
tool. GuardRyle denies failed checks, and a failed result is never authorized.
Never treat `REVIEW` as permission to continue automatically.
