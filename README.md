# Previsia — Backend

Plataforma de inteligência preditiva para gestão de cobranças (projeto acadêmico).

Stack: **Python 3.11 + UV** · **Jupyter** para data engineering & ML · **FastAPI + JWT** para API · **Supabase** (Postgres) · **Groq** (LLM) · **IBM Code Engine** para deploy.

---

## Arquitetura de dados — Medallion

```
notebooks/data/
├── bronze/    ← arquivos brutos (CSV/XLSX) + snapshot parquet sem limpeza
├── silver/    ← contracts.parquet, payments.parquet (limpos, tipados, snake_case)
└── gold/      ← contract_features.parquet, payments_features.parquet (ML-ready)
```

Cada notebook em `notebooks/01_pipeline/` lê da camada anterior e escreve na próxima.

---

## Estrutura do projeto

```
previsia-api/
├── notebooks/
│   ├── data/                     ← raw + bronze/silver/gold parquet
│   ├── 01_pipeline/              ← ETL em estilo descoberta progressiva
│   │   ├── 01_bronze_ingestion.ipynb
│   │   ├── 02_silver_cleaning.ipynb
│   │   ├── 03_gold_features.ipynb
│   │   ├── 04_supabase_load.ipynb
│   │   └── 05_eda_analytics.ipynb
│   ├── 02_ml/                    ← Treino dos 4 modelos (a fazer)
│   └── 03_evaluation/            ← Relatórios SHAP & comparações (a fazer)
├── src/
│   ├── shared/                   ← Utilidades importadas pelos notebooks
│   ├── api/                      ← FastAPI (com JWT auth)
│   └── insights/                 ← Cadeias LLM (Groq)
├── sql/
│   └── 001_schema.sql            ← Migração inicial (sem Alembic)
├── models/                       ← Artefatos .joblib treinados
└── reports/                      ← HTML / CSV de avaliação e DQ
```

---

## Setup

```bash
# 1. dependências
uv sync

# 2. variáveis de ambiente
cp .env.example .env
# preencher DATABASE_URL, GROQ_API_KEY, JWT_SECRET

# 3. schema no Supabase (uma vez)
psql "$DATABASE_URL" -f sql/001_schema.sql

# 4. abrir Jupyter
uv run jupyter lab
```

---

## Ordem de execução do pipeline

| # | Notebook | Lê | Escreve |
|---|---|---|---|
| 1 | `01_bronze_ingestion.ipynb` | `data/bronze/*.{csv,xlsx}` | `data/bronze/*.parquet` |
| 2 | `02_silver_cleaning.ipynb` | `data/bronze/*.parquet` | `data/silver/*.parquet` |
| 3 | `03_gold_features.ipynb` | `data/silver/*.parquet` | `data/gold/*.parquet` |
| 4 | `04_supabase_load.ipynb` | `data/silver` + `data/gold` | Postgres (Supabase) |
| 5 | `05_eda_analytics.ipynb` | `data/silver` + `data/gold` | `reports/data_quality_report.csv` |

**Status atual:** notebooks 1, 2, 3 e 5 já testados executando ponta-a-ponta. As 10 expectativas de qualidade passam.

---

## Autenticação (em `src/api/`)

- JWT (HS256) com `JWT_SECRET` no `.env`
- Endpoints públicos: `POST /auth/register`, `POST /auth/login`, `GET /health`
- Todos os outros endpoints exigem `Authorization: Bearer <token>`
- Tabela `users` no Supabase com `password_hash` (bcrypt)

---

## Deploy (resumo)

- **API**: build de imagem (`Dockerfile` na raiz), push para `icr.io`, deploy via `ibmcloud ce app create`.
- **Pipeline de dados**: executado localmente nos notebooks (acadêmico) — quando agendado, via GitHub Actions `papermill` rodando cada `.ipynb`.
