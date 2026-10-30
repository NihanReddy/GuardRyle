# GuardRyle Control Room

A responsive React + TypeScript dashboard for monitoring GuardRyle guardrail activity.

## Run locally

From this directory:

```bash
npm install
npm run dev
```

The Vite server normally runs at `http://localhost:5173/`.
The development server proxies `/api` requests to
`http://127.0.0.1:8000`. Start the backend from the repository root with
`python -m uvicorn guardrail_middleware.api:app --reload` before opening the
Settings panel.

Create a production build with:

```bash
npm run build
```

## Dashboard surface

- Workspace navigation for overview, event logs, policies, and evaluations
- Blocked, review, allowed, and policy-accuracy summary metrics
- Request-volume area chart with selectable time range
- Evaluation accuracy donut and category score bars
- Recent event table with status filters and review modal
- JSON/YAML policy upload controls
- Policy health, versions, and coverage panel
- Runtime provider/model status and secure OpenAI settings in the existing Settings panel
- Responsive layout for desktop and narrow screens

The dashboard fetches `/api/dashboard` from the backend. The endpoint keeps
the repository evaluation snapshot as a baseline and merges persisted runtime
evaluation events from the SQLite operational store. Regenerate the baseline
artifacts from the repository root after policy, dataset, or comparison report
changes:

```bash
python scripts/export_dashboard_data.py
```

The upload control validates local JSON policy structure and reports the selected file. Review actions and filters are session-local until a backend API is connected.

When an API server is connected, the Settings panel reads `/api/embedding/status`
and `/api/embedding/providers`, and uses `/api/embedding/config` for confirmed
provider changes. OpenAI credentials use `/api/providers/openai/status`,
`/api/providers/openai/key`, and `/api/providers/openai/test`. The key field is
cleared after a successful save; it is not persisted in browser storage or
returned by the API. A missing API server is shown as unavailable rather than
being replaced with mocked model data. Required security evaluation failures
remain fail-closed and are shown as REVIEW/degraded status.

For local development only, protected configuration requests can include
`VITE_GUARDRYLE_ADMIN_TOKEN` in the Vite environment. Do not embed an
administrative token in a production bundle; use a same-origin authenticated
session or reverse proxy instead. The OpenAI API key is never a frontend
environment variable.
