FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

COPY pyproject.toml README.md ./
COPY guardrail_middleware ./guardrail_middleware
COPY policy.json guardrail_config.json ./
COPY data/representative_dataset.json ./data/representative_dataset.json
COPY reports/rules_vs_semantic_comparison.json ./reports/rules_vs_semantic_comparison.json
COPY scripts ./scripts

RUN python -m pip install --no-cache-dir .

EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn guardrail_middleware.api:app --host 0.0.0.0 --port ${PORT} --no-access-log"]
