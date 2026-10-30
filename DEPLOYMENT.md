# GuardRyle deployment

GuardRyle should run behind a TLS-terminating reverse proxy or a private
service-to-service network. The administrative token must be configured as a
server-side secret; it must never be embedded in frontend JavaScript.

## Configuration

Required:

```text
GUARDRYLE_ADMIN_TOKEN=<long-random-token>
GUARDRYLE_CORS_ORIGINS=https://dashboard.example.com
```

Optional:

```text
GUARDRYLE_POLICY_PATH=/app/policy.json
GUARDRYLE_RUNTIME_DB=/var/lib/guardryle/runtime.sqlite3
GUARDRYLE_CONFIG_PATH=/app/guardrail_config.json
OPENAI_API_KEY=<secret-managed-provider-key>
OPENAI_EMBEDDING_MODEL=<embedding-model>
OPENAI_EMBEDDING_DIMENSIONS=1536
```

Use the platform secret manager for all credentials. Do not commit `.env`
files, API keys, or the runtime SQLite database.

To use the real remote embedding path, set `primary_provider` to `openai` in
the runtime configuration and provide `OPENAI_API_KEY`. The API registers the
provider only when the key is present; readiness fails when the configured
provider is unavailable.

## Container

Build and run a single-instance pilot:

```bash
docker build -t guardryle:local .
docker run --rm -p 8000:8000 \
  -e GUARDRYLE_ADMIN_TOKEN="$(openssl rand -hex 32)" \
  -e GUARDRYLE_CORS_ORIGINS="https://dashboard.example.com" \
  -v guardryle-data:/var/lib/guardryle \
  guardryle:local
```

Check the process:

```bash
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
```

`/health/live` only confirms that the process is responding. `/health/ready`
returns HTTP 503 until a policy, healthy configured provider, and admin token
are available.

The bundled SQLite store is for a single instance or pilot deployment. Replace
`OperationalStore` with a shared production store before running multiple
replicas.

## Service-to-service evaluation

The chat application's backend, not the browser, should call:

```http
POST /api/evaluate
Authorization: Bearer <server-side-admin-token>
Content-Type: application/json
```

```json
{
  "text": "message to evaluate",
  "required_security_check": true,
  "policy_id": "production-policy-v1"
}
```

Evaluate user input before calling the LLM and evaluate the generated output
before returning it. Treat both `deny` and `review` as non-approval. Use
`required_security_check: true` for sensitive actions and tool calls.

For a Python chat backend, the SDK adapter can wrap OpenAI directly:

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
response = await chat.complete([
    ChatMessage(role="user", content=user_message),
])
print(response.content)
```

The adapter checks the user input before the OpenAI request and checks the
generated output before it is returned. A `GuardrailBlockedError` is raised for
both `deny` and `review`.

Security checks fail closed by default. If a provider or evaluator fails, the
result is `deny`, including for ordinary evaluations. The legacy
`allow_degraded_guardrail` setting cannot authorize a failed check.

The dashboard currently has no server-side user authentication. Do not expose
the administrative API token through a `VITE_*` variable or a public browser
bundle. Put an authenticated backend-for-frontend in front of administrative
operations.

## Production process

Do not use `--reload` in production. Run the container command supplied in the
Dockerfile, or use an equivalent process manager with one or more workers.
Expose `/health/live` to the platform liveness probe and `/health/ready` to
the readiness probe. Keep the SQLite volume on durable storage for a pilot;
use a shared database before scaling beyond one replica.
