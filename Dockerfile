# ── stage 1: dependências ──────────────────────────────────────────────────────
FROM python:3.11-slim AS deps

WORKDIR /app

RUN pip install uv --no-cache-dir

COPY pyproject.toml uv.lock README.md ./

# instala somente o grupo de produção (sem jupyterlab, pytest, etc.)
RUN uv sync --no-dev --frozen

# ── stage 2: runtime ───────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# copia o venv pronto do stage anterior
COPY --from=deps /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# código-fonte da API + utilitários compartilhados
COPY src/ ./src/

# modelos treinados (artefatos joblib necessários para inferência)
COPY models/ ./models/

# schema SQL (útil para documentação / migrações on-deploy)
COPY sql/ ./sql/

# usuário sem root
RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8080

# IBM Code Engine usa a porta via env PORT; fallback 8080
CMD ["sh", "-c", "uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
