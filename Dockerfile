# ── stage 1: dependências ──────────────────────────────────────────────────────
FROM python:3.11-slim AS deps

WORKDIR /app

RUN pip install uv --no-cache-dir

COPY pyproject.toml uv.lock README.md ./

# instala APENAS as dependências do [project] (sem notebook/dev)
RUN uv sync --no-default-groups --no-dev --frozen

# ── stage 2: runtime ───────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# libgomp1 é exigida por xgboost/lightgbm em runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=deps /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# código + artefatos necessários para inferência
COPY src/    ./src/
COPY models/ ./models/
COPY sql/    ./sql/

RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8080

# Code Engine injeta PORT; fallback 8080
CMD ["sh", "-c", "uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
