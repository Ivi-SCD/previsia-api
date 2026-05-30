# Previsia — Plataforma de Inteligência Preditiva para Cobrança de Dívidas

Projeto acadêmico que demonstra o ciclo completo de uma plataforma de dados em produção: do arquivo bruto até uma API REST autenticada em nuvem pública, passando por engenharia de dados (arquitetura medalhão), modelagem preditiva (4 modelos de ML), explicabilidade e um agente LLM orquestrado com LangGraph para perguntas em linguagem natural sobre a carteira.

**API em produção:** https://previsia-api.2ai3ui4gvmwq.us-south.codeengine.appdomain.cloud
**Documentação interativa (Swagger):** [`/docs`](https://previsia-api.2ai3ui4gvmwq.us-south.codeengine.appdomain.cloud/docs)

---

## Sumário

1. [Problema de negócio](#1-problema-de-negócio)
2. [Conjuntos de dados](#2-conjuntos-de-dados)
3. [Stack tecnológica e justificativa](#3-stack-tecnológica-e-justificativa)
4. [Arquitetura geral](#4-arquitetura-geral)
5. [Engenharia de dados — arquitetura medalhão](#5-engenharia-de-dados--arquitetura-medalhão)
6. [Modelos preditivos](#6-modelos-preditivos)
7. [API REST com autenticação JWT](#7-api-rest-com-autenticação-jwt)
8. [Insights com LLM e o agente Text-to-SQL com LangGraph](#8-insights-com-llm-e-o-agente-text-to-sql-com-langgraph)
9. [Infraestrutura e deploy](#9-infraestrutura-e-deploy)
10. [Reprodutibilidade — como rodar do zero](#10-reprodutibilidade--como-rodar-do-zero)
11. [Estrutura do repositório](#11-estrutura-do-repositório)
12. [Validação automatizada e segurança](#12-validação-automatizada-e-segurança)
13. [Decisões de projeto comentadas](#13-decisões-de-projeto-comentadas)

---

## 1. Problema de negócio

**Contexto:** uma carteira de cobrança terceirizada possui 10.000 contratos de inadimplência distribuídos entre quatro assessorias e cinco regiões do Brasil, somando **R$ 62,3 milhões inadimplentes**. Para cada contrato existe um plano de parcelamento (totalizando 100 mil parcelas) com diferentes formas de pagamento (Boleto, Pix, Débito Automático).

**Perguntas que a plataforma responde:**

| # | Pergunta | Quem usa | Saída |
|---|----------|----------|-------|
| 1 | Esse contrato vai ter recuperação **acima da mediana** da carteira? | Operação (priorização) | Probabilidade + classificação |
| 2 | Essa parcela aberta é de **alto ticket**? | Time de cobrança ativa | Classificação binária |
| 3 | **Quanto** (R$) será recuperado deste contrato? | Tesouraria (forecast) | Valor estimado |
| 4 | **Quanto tempo** falta para fechar em acordo? | Planejamento de capacidade | Curva de sobrevivência |
| 5 | "Quanto a Vértice recuperou no Sudeste no último mês?" | Gestão executiva | Resposta em PT-BR via LLM |

A solução completa entrega: ETL governado, 4 modelos preditivos com métricas auditáveis, API REST autenticada, agente LLM com SQL seguro e deploy serverless 24/7.

---

## 2. Conjuntos de dados

Dois arquivos brutos, totalizando ~110 mil registros:

### `cobranca_assessorias.csv` — 10.000 contratos, 8 colunas

| Coluna | Tipo | Domínio observado |
|--------|------|-------------------|
| `ID_Contrato` | string | `CONTR_2026_NNNNN` (chave primária, único) |
| `Nome_Assessoria` | string | 4 valores reais (com sujeira: `Fênix` vs `fênix`, espaço final em `Vértice `) |
| `Data_Envio_Assessoria` | data | jan/2026 a abr/2026 |
| `Dias_Em_Atraso_Inicial` | inteiro | 1 a 9999, com sentinela `-999` em 0,5% das linhas |
| `Valor_Inadimplente_Inicial` | string | **misturado**: `R$ 25.007,89` e `4295.12` |
| `Status_Cobranca` | categórico | Em Aberto, Acordo Firmado, Insucesso, Ajuizado |
| `Score_Interno_Risco` | float | 1–100, com 3% de nulos |
| `Regiao_Cliente` | categórico | 5 regiões BR (com sujeira de caixa: `NORDESTE`) |

### `fluxo_pagamentos.xlsx` — 100.000 parcelas, 9 colunas

| Coluna | Tipo | Observações |
|--------|------|-------------|
| `ID_Pagamento` | string | chave primária |
| `ID_Contrato` | string | FK para `cobranca_assessorias` — 100% de cobertura, zero órfãos |
| `Numero_Parcela` | inteiro | 1 a 23 por contrato |
| `Data_Vencimento` | data (mas vem como **texto** no Excel) | jan/2025 a mar/2026 |
| `Data_Pagamento` | data ou nulo | nulo significa parcela não paga (27% dos casos) |
| `Valor_Parcela` | inteiro | 5 valores: 450, 600, 850, 1200, 1500 |
| `Valor_Pago` | float | varia bastante: ≈ 0,73 × valor_parcela + ruído |
| `Forma_Pagamento` | categórico | Boleto (50%), Pix (35%), Débito Automático (15%) |
| `Indicador_Contemplado` | `Sim`/`Não` | True/False após normalização |

### Particularidades importantes

- **Mistura de formatos monetários:** o parser `src/shared/parsing.py` lida com R$ BR e decimal americano na mesma coluna.
- **Sentinela `-999`:** tratado como `NaN` em `silver`.
- **Datas como string no Excel:** descobertas durante a limpeza silver e convertidas explicitamente com `pd.to_datetime(errors='coerce')`.
- **Imputação por contexto:** os 3% de nulos em `Score_Interno_Risco` são imputados com a **mediana do recorte (região × assessoria)** e não com a média global — preserva diferenças regionais de risco.

---

## 3. Stack tecnológica e justificativa

| Camada | Tecnologia | Por quê |
|--------|------------|---------|
| Linguagem | Python 3.11 | Ecossistema de dados maduro |
| Gerenciador de deps | **UV** | 10× mais rápido que pip, lock file determinístico |
| Análise/ETL | Jupyter + pandas + plotly | Notebook é o formato natural para descoberta progressiva |
| Armazenamento intermediário | Apache Parquet | Colunar, comprimido, tipado, ~10× menor que CSV |
| Persistência | Supabase (PostgreSQL gerenciado) | Free tier real (500MB), API SQL pura |
| ML — gradient boosting | XGBoost + LightGBM | Estado da arte em dados tabulares |
| ML — sobrevivência | lifelines (Cox PH) | Único framework Python maduro para survival analysis |
| Serialização de modelos | joblib | Padrão sklearn, compatível com numpy |
| API | FastAPI + Uvicorn | Async, validação Pydantic, OpenAPI gratuito |
| Autenticação | JWT (HS256) + bcrypt | Stateless, padrão da indústria |
| LLM provider | Groq (Llama 3.3 70B) | Latência <2s, plano gratuito generoso |
| Orquestração LLM | **LangGraph** | Workflows de agentes com estado tipado |
| Container | Docker multi-stage | Imagem final enxuta (298 MB comprimido) |
| Deploy | IBM Code Engine | Serverless, scale-to-zero, 100% free tier |
| Registry | IBM Container Registry | Integrado ao CE, 512MB free |

---

## 4. Arquitetura geral

```
┌─────────────────────────┐      ┌─────────────────────────┐
│  Arquivos brutos        │      │  Notebooks Jupyter      │
│  CSV + XLSX             │─────▶│  01_pipeline/           │
└─────────────────────────┘      │  bronze → silver → gold │
                                 └────────────┬────────────┘
                                              │ upsert
                                              ▼
                                 ┌─────────────────────────┐
                                 │  Supabase PostgreSQL    │
                                 │  6 tabelas              │
                                 └────────────┬────────────┘
                                              │ leitura
                                              │
┌─────────────────────────┐      ┌─────────────▼───────────┐
│  Notebooks 02_ml/       │      │  FastAPI                │
│  treina 4 modelos       │─────▶│  (IBM Code Engine)      │
│  → models/*.joblib      │      │                         │
└─────────────────────────┘      │  /auth/*  (JWT)         │
                                 │  /analytics/*           │
┌─────────────────────────┐      │  /predict/*             │
│  Groq (Llama 3.3 70B)   │◀─────┤  /insights/* (LangGraph)│
└─────────────────────────┘      └─────────────────────────┘
                                              ▲
                                              │ Bearer token
                                 ┌────────────┴────────────┐
                                 │ Cliente HTTP (Postman,  │
                                 │ curl, Swagger UI)       │
                                 └─────────────────────────┘
```

**Princípios:**

- **Separação ETL ↔ API:** notebooks fazem o trabalho de dados; a API é stateless e só serve inferência + analytics.
- **Idempotência:** `INSERT … ON CONFLICT DO UPDATE` permite re-rodar a carga sem efeitos colaterais.
- **Imutabilidade de bronze:** uma vez salvo, bronze nunca é alterado — todas as transformações vivem em silver/gold.
- **Defesa em profundidade:** JWT, validação Pydantic, SQL allow-list no agente LLM, container sem root.

---

## 5. Engenharia de dados — arquitetura medalhão

A arquitetura medalhão (popularizada pela Databricks) divide o pipeline em três camadas com responsabilidades distintas. Implementação em `notebooks/01_pipeline/`:

### 🥉 Bronze — fidelidade ao bruto (`01_bronze_ingestion.ipynb`)

- Lê CSV e XLSX **sem julgamento**: nenhuma limpeza de conteúdo.
- Converte para Parquet preservando todos os tipos originais (mesmo os errados).
- Exporta `data/bronze/*.parquet` como **snapshot datado** da origem.
- **Por que parquet?** Colunar, comprimido (~3× menor que CSV), tipado, lido em segundos por pandas/Spark.

### 🥈 Silver — limpo e padronizado (`02_silver_cleaning.ipynb`)

O notebook é escrito em **estilo descoberta progressiva**: não enuncia os problemas no início, vai descobrindo coluna por coluna com `value_counts()` e `describe()`, aplicando o tratamento conforme aparece. Isso reproduz o que um analista de dados faz na prática.

Tratamentos aplicados:

| Problema descoberto | Tratamento |
|---------------------|-----------|
| `Fênix` vs `fênix`, espaço final em `Vértice ` | `.str.strip().str.title()` |
| `R$ 25.007,89` misturado com `4295.12` | parser BR/EN unificado (`src/shared/parsing.py`) |
| Sentinela `-999` em `Dias_Em_Atraso_Inicial` | `where(>0)` → `NaN` (`Int64` nullable) |
| 300 nulos em `Score_Interno_Risco` | mediana por (região × assessoria), fallback global |
| `Indicador_Contemplado` texto `Sim/Não` | `.map({'Sim': True, 'Não': False})` |
| Datas como `object` no Excel | `pd.to_datetime(errors='coerce')` |
| `snake_case` em todo lugar | renomeação de colunas |

Saída: `data/silver/contracts.parquet`, `data/silver/payments.parquet`. **Integridade referencial:** verificada via set comparison (`set(payments.id_contrato) ⊆ set(contracts.id_contrato)`) — 100% de cobertura, zero órfãos.

### 🥇 Gold — pronto para ML (`03_gold_features.ipynb`)

Agrega 100k parcelas → 10k features por contrato. Features derivadas:

- `parcelas_total` / `parcelas_pagas` / `total_pago` — agregações simples
- `taxa_adimplencia` = `parcelas_pagas / parcelas_total`
- `media_dias_atraso` — entre parcelas efetivamente pagas
- `metodo_predominante` — moda de `forma_pagamento`
- `velocidade_pagamento` = `total_pago / dias desde 1º pagamento` (R$/dia)
- `taxa_adimplencia_historica` por parcela — cumulativo **estritamente anterior** para evitar *data leakage*
- `faixa_valor` (baixo/médio/alto/muito_alto) e `dias_atraso_bucket` para uso em dashboards
- `label_sucesso` — só para casos fechados (`Acordo Firmado` = True, `Insucesso` = False)

### Carga no Supabase (`04_supabase_load.ipynb`)

- Esquema declarado em `sql/001_schema.sql` (6 tabelas + índices)
- Upsert idempotente em lotes (1k–2k linhas) via `INSERT … ON CONFLICT DO UPDATE`
- Registro de execução em `pipeline_runs` (start, end, rowcount, status)

### EDA + qualidade de dados (`05_eda_analytics.ipynb`)

10 expectativas automáticas (estilo Great Expectations inline) bloqueiam o pipeline se quebrarem:

- Chaves primárias únicas e não-nulas
- Domínios fechados de `status_cobranca`, `regiao`, `forma_pagamento`
- Faixas válidas: `score_risco ∈ [0,100]`, `taxa_adimplencia ∈ [0,1]`
- Integridade referencial `payments → contracts`

---

## 6. Modelos preditivos

Quatro modelos cobrem três tipos de problema (classificação, regressão e análise de sobrevivência) com objetivos de negócio distintos. Todos em `notebooks/02_ml/`, com artefatos joblib em `models/`.

### Modelo A — Classificador de Alta Recuperação (`01_classifier_success.ipynb`)

| Item | Detalhe |
|------|---------|
| **Pergunta** | O contrato vai recuperar mais do que a mediana da carteira (R$ 5.340)? |
| **Tipo** | Classificação binária |
| **Target** | `total_pago >= mediana(total_pago)` |
| **Algoritmo** | XGBoost (`enable_categorical=True`) |
| **Features** | 8 numéricas (score, atraso, parcelas, velocidade…) + 5 categóricas |
| **Split** | 80/20 estratificado |
| **Métricas (teste)** | **Accuracy 0,904 · ROC-AUC 0,965 · F1-macro 0,903** |
| **Feature mais importante** | `velocidade_pagamento` (correlação 0,92 com o target) |

### Modelo B — Classificador de Parcela de Alto Ticket (`02_payment_default.ipynb`)

| Item | Detalhe |
|------|---------|
| **Pergunta** | Essa parcela vai gerar pagamento acima da mediana entre as pagas (R$ 553)? |
| **Tipo** | Classificação binária |
| **Target** | `valor_pago > mediana(valor_pago entre pagas)` |
| **Algoritmo** | LightGBM com `class_weight='balanced'` |
| **N** | 100.000 parcelas |
| **Métricas (teste)** | **Accuracy 0,805 · ROC-AUC 0,859 · PR-AUC 0,70** |

> **Nota técnica:** o teto teórico de R² para predizer `valor_pago` neste dataset é ~0,79 devido ao componente estocástico no valor de cada parcela (σ ≈ R$ 270 por parcela paga). 0,86 AUC é próximo do limite analítico para a tarefa.

### Modelo C — Regressão de Valor Recuperado (`03_recovery_amount.ipynb`)

| Item | Detalhe |
|------|---------|
| **Pergunta** | Qual o R$ total que será recuperado do contrato? |
| **Tipo** | Regressão |
| **Target** | `total_pago` (linear, sem transformação) |
| **Algoritmo** | XGBoost Regressor com early stopping (50 rounds) |
| **Feature engineering** | `valor_medio_parcela = valor_inadimplente / parcelas_total`, `recuperacao_estimada = parcelas_pagas × valor_medio_parcela × 0,73` (proxy físico) |
| **Métricas (teste)** | **R² 0,905 · MAE R$ 493 · RMSE R$ 678** |

### Modelo D — Análise de Sobrevivência Cox PH (`04_survival.ipynb`)

| Item | Detalhe |
|------|---------|
| **Pergunta** | Quanto tempo até o contrato fechar em acordo? |
| **Tipo** | Survival analysis |
| **Evento** | `status_cobranca == 'Acordo Firmado'` (1 = evento, 0 = censurado) |
| **Tempo** | `min(último_pagamento, hoje) - data_envio` (em dias) |
| **Algoritmo** | Cox Proportional Hazards (`lifelines`) com penalizer L2 = 0,1 |
| **Métrica** | Concordance index = 0,521 |

> **Observação acadêmica:** o C-index baixo evidencia que, neste dataset, o tempo até evento é praticamente independente das features observáveis. O modelo é apresentado como demonstração de metodologia (curvas de sobrevivência, riscos proporcionais) — em dados reais com fatores macroeconômicos seria muito mais informativo.

### Resumo das métricas

| Modelo | Tipo | Métrica principal | Valor |
|--------|------|-------------------|-------|
| A — Alta Recuperação | classificação | ROC-AUC | **0,965** |
| C — Valor Recuperado | regressão | R² | **0,905** |
| B — Alto Ticket | classificação | ROC-AUC | 0,859 |
| D — Sobrevivência | survival | C-index | 0,521 |

---

## 7. API REST com autenticação JWT

Implementação em `src/api/`. Auto-documentada via OpenAPI em `/docs`.

### Endpoints

| Método | Rota | Auth | Descrição |
|--------|------|------|-----------|
| GET | `/health` | público | Status do serviço + ping no banco |
| POST | `/auth/register` | público | Cria usuário (email único, senha ≥ 8 chars, bcrypt) |
| POST | `/auth/login` | público | Retorna JWT (HS256, exp 60 min) |
| GET | `/me` | JWT | Devolve o usuário do token |
| GET | `/analytics/portfolio` | JWT | KPIs agregados da carteira |
| GET | `/analytics/agencies` | JWT | Ranking de assessorias |
| POST | `/predict/collection-success` | JWT | Inferência do Modelo A |
| POST | `/insights/explain/{id_contrato}` | JWT | Explicação em PT-BR via LLM |
| POST | `/insights/portfolio-summary` | JWT | Narrativa executiva via LLM |
| POST | `/insights/ask` | JWT | Pergunta em PT-BR → SQL → resposta (LangGraph) |

### Fluxo de autenticação

```
1. POST /auth/register {email, password, full_name}
   → 201 + user (id, email, role='analyst')

2. POST /auth/login {email, password}
   → 200 + access_token (JWT HS256, exp 60 min)

3. GET /me com header "Authorization: Bearer <token>"
   → 200 + user

4. Sem token ou com token inválido/expirado:
   → 401 {"detail": "Credenciais inválidas"}
```

### Segurança

- **Senha:** bcrypt (cost factor padrão 12) — nunca armazenada em texto puro
- **JWT:** chave secreta de 256 bits, algoritmo `HS256`, claim `sub` = email + `uid`
- **Validação Pydantic:** rejeita payloads malformados antes de tocar no banco (422)
- **Container sem root:** usuário `appuser` no Dockerfile
- **Connection pooling:** `pool_pre_ping=True` na engine SQLAlchemy

---

## 8. Insights com LLM e o agente Text-to-SQL com LangGraph

A camada `src/insights/` contém três funcionalidades LLM (Groq + Llama 3.3 70B), expostas em `/insights/*`.

### 8.1 Risk Explainer — `/insights/explain/{id_contrato}`

1. Busca o contrato em `contract_features` + `contracts`
2. Roda o Modelo A para obter a probabilidade
3. Extrai os 3 top fatores via `feature_importances_` do XGBoost
4. Monta um contexto estruturado (score, fatores, atraso, valor, região, assessoria, status)
5. Envia ao Groq com prompt sistema PT-BR de "analista sênior de cobrança"
6. Devolve `score`, `risk_level` (ALTO/MÉDIO/BAIXO), `top_factors`, `explanation_pt`

### 8.2 Portfolio Summary — `/insights/portfolio-summary`

1. Executa 3 queries agregadas no Supabase (KPIs, top região, melhor assessoria)
2. Constrói contexto narrativo
3. LLM gera resumo executivo PT-BR em 2 parágrafos

### 8.3 Text-to-SQL Agent com **LangGraph** — `/insights/ask`

Este é o componente mais sofisticado: um **grafo de estado tipado** (LangGraph) que orquestra 4 nós:

```
              ┌──────────────────┐
              │   question (PT)  │
              └────────┬─────────┘
                       ▼
              ┌──────────────────┐
              │  generate_sql    │  ◀── LLM (temperature=0)
              │                  │      schema do banco no system prompt
              └────────┬─────────┘
                       ▼
              ┌──────────────────┐
              │  validate_sql    │  ◀── regex allow-list (SELECT only)
              │                  │      injeta LIMIT 100 se faltar
              └────────┬─────────┘
                       │
            erro ◀─────┤────▶ ok
              │        ▼
              │   ┌──────────────────┐
              │   │   execute_sql    │  ◀── SQLAlchemy + Postgres
              │   └────────┬─────────┘
              │            ▼
              │   ┌──────────────────┐
              │   │  format_answer   │  ◀── LLM (temperature=0.2)
              │   └────────┬─────────┘
              ▼            ▼
              └────────────┘
                    END
```

**Estado tipado** (`TypedDict`):

```python
class SQLState(TypedDict, total=False):
    question:         str
    sql:              str
    validation_error: str
    rows:             list[dict]
    answer:           str
```

**Camadas de defesa contra SQL injection:**

1. Prompt sistema instrui o LLM a gerar **apenas** SELECT
2. Regex bloqueia `INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|COPY|VACUUM`
3. Verificação de início: precisa começar com `SELECT` ou `WITH`
4. Injeção automática de `LIMIT 100` se a query não tiver limite
5. Conexão de leitura (DRY: a mesma `engine` da API, mas o usuário Supabase pode ser configurado como read-only)
6. Tipos não-JSON (Decimal, datetime) são serializados como string antes de retornar

**Por que LangGraph e não chain simples?**

- Estado tipado e auditável (cada nó devolve um delta)
- Permite ramificações condicionais futuras (ex: re-tentativa se SQL falhar)
- Nós são funções puras → fáceis de testar isoladamente
- Permite adicionar nós de observabilidade (tracing) sem alterar a lógica

---

## 9. Infraestrutura e deploy

### IBM Code Engine (serverless)

| Recurso | Configuração |
|---------|--------------|
| Região | `us-south` |
| Projeto | `previsia` |
| App | `previsia-api` |
| CPU/RAM | 1 vCPU · 2 GB |
| Scaling | min 0, max 2 |
| Timeout | 300s |
| Imagem | `us.icr.io/previsia/previsia-api:v1` (298 MB comprimido) |
| Segredos | `previsia-env` (Code Engine secret) |
| Pull credentials | API key IAM dedicada |

### Otimização da imagem Docker

Build em **multi-stage** (`Dockerfile`):

1. **Stage `deps`:** `python:3.11-slim` + `uv sync --no-default-groups --no-dev --frozen` → instala só o runtime essencial.
2. **Stage `runtime`:** copia `.venv` pronto, adiciona `libgomp1` (necessário para xgboost/lightgbm), código + modelos, roda como usuário não-root.

| Decisão | Impacto |
|---------|---------|
| `xgboost-cpu` em vez de `xgboost` | -394 MB (libs NVIDIA CUDA removidas) |
| `lifelines` movido para `dependency-groups.notebook` | -50 MB |
| `pyarrow`, `openpyxl`, `plotly`, `matplotlib`, `shap`, `great-expectations` fora do runtime | -800 MB |
| Multi-stage com cache de deps | rebuilds de código em <30s |
| **Total:** | **4,79 GB → 298 MB comprimido (95% de redução)** |

### Separação `dependencies` × `dependency-groups`

`pyproject.toml`:

- `[project.dependencies]` — runtime API (cabem no container)
- `[dependency-groups.notebook]` — só localmente para Jupyter
- `[dependency-groups.dev]` — só localmente para teste

```bash
uv sync                              # tudo (dev local)
uv sync --no-default-groups --no-dev # só runtime (CI / Docker)
```

---

## 10. Reprodutibilidade — como rodar do zero

### Pré-requisitos
- Python 3.11
- [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Docker (para build local da imagem)
- Conta gratuita Supabase (DATABASE_URL)
- Conta gratuita Groq (GROQ_API_KEY)

### Setup

```bash
# 1. clone e dependências
git clone git@github.com:Ivi-SCD/previsia-api.git
cd previsia-api
uv sync

# 2. variáveis de ambiente
cp .env.example .env
# preencher DATABASE_URL, GROQ_API_KEY, JWT_SECRET (mínimo 32 chars)

# 3. schema no Supabase
psql "$DATABASE_URL" -f sql/001_schema.sql

# 4. abrir Jupyter para rodar pipeline e treinos
uv run jupyter lab
```

### Ordem de execução dos notebooks

| # | Notebook | Lê | Escreve |
|---|----------|-----|---------|
| 1 | `01_pipeline/01_bronze_ingestion.ipynb` | `data/bronze/*.{csv,xlsx}` | `data/bronze/*.parquet` |
| 2 | `01_pipeline/02_silver_cleaning.ipynb` | bronze parquet | `data/silver/*.parquet` |
| 3 | `01_pipeline/03_gold_features.ipynb` | silver parquet | `data/gold/*.parquet` |
| 4 | `01_pipeline/04_supabase_load.ipynb` | silver + gold | Postgres |
| 5 | `01_pipeline/05_eda_analytics.ipynb` | silver + gold | `reports/data_quality_report.csv` |
| 6 | `02_ml/01_classifier_success.ipynb` | gold | `models/collection_success_v1.joblib` |
| 7 | `02_ml/02_payment_default.ipynb` | gold | `models/payment_default_v1.joblib` |
| 8 | `02_ml/03_recovery_amount.ipynb` | gold | `models/recovery_amount_v1.joblib` |
| 9 | `02_ml/04_survival.ipynb` | gold | `models/survival_v1.joblib` |

### Rodar a API localmente

```bash
uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
# Swagger: http://localhost:8000/docs
```

### Validação end-to-end

```bash
# em outra aba, com a API rodando:
uv run python scripts/validate.py --base-url http://localhost:8000
# ou contra produção:
uv run python scripts/validate.py --base-url https://previsia-api.2ai3ui4gvmwq.us-south.codeengine.appdomain.cloud
```

### Build e deploy no IBM Code Engine

```bash
# login
ibmcloud login --sso
ibmcloud target -g Default -r us-south
ibmcloud cr login

# build + push
docker build -t us.icr.io/previsia/previsia-api:v1 .
docker push us.icr.io/previsia/previsia-api:v1

# deploy / update
ibmcloud ce app update --name previsia-api \
  --image us.icr.io/previsia/previsia-api:v1
```

---

## 11. Estrutura do repositório

```
previsia-api/
├── Dockerfile                       # multi-stage, runtime enxuto
├── .dockerignore                    # exclui notebooks, dados, .env
├── .env.example                     # template (sem valores reais)
├── .gitignore                       # exclui .env, models/*.joblib, data
├── .python-version                  # 3.11
├── pyproject.toml                   # deps separadas em runtime/notebook/dev
├── uv.lock                          # lock file determinístico
├── README.md                        # este arquivo
│
├── notebooks/                       # toda a engenharia de dados e ML
│   ├── data/
│   │   ├── bronze/                  # CSV + XLSX brutos + snapshot parquet
│   │   ├── silver/                  # parquets limpos e tipados
│   │   └── gold/                    # parquets com features ML-ready
│   ├── 01_pipeline/
│   │   ├── 01_bronze_ingestion.ipynb
│   │   ├── 02_silver_cleaning.ipynb
│   │   ├── 03_gold_features.ipynb
│   │   ├── 04_supabase_load.ipynb
│   │   └── 05_eda_analytics.ipynb
│   ├── 02_ml/
│   │   ├── 01_classifier_success.ipynb   # Modelo A
│   │   ├── 02_payment_default.ipynb      # Modelo B
│   │   ├── 03_recovery_amount.ipynb      # Modelo C
│   │   └── 04_survival.ipynb             # Modelo D
│   └── 03_evaluation/               # (espaço para relatórios SHAP/PR-curves)
│
├── src/                             # código de produção
│   ├── config.py                    # Settings via pydantic-settings
│   ├── shared/
│   │   └── parsing.py               # parse_brl() — usado por notebooks e API
│   ├── api/
│   │   ├── main.py                  # FastAPI entrypoint
│   │   ├── db.py                    # engine SQLAlchemy + get_db()
│   │   ├── security.py              # JWT + bcrypt + get_current_user()
│   │   ├── schemas.py               # Pydantic models
│   │   └── routers/
│   │       ├── auth.py              # /auth/register, /auth/login
│   │       ├── me.py                # /me
│   │       ├── analytics.py         # /analytics/*
│   │       ├── predict.py           # /predict/*
│   │       └── insights.py          # /insights/*
│   └── insights/
│       ├── llm.py                   # cliente ChatGroq centralizado
│       ├── explainer.py             # Risk Explainer
│       ├── portfolio_summary.py     # Narrativa executiva
│       └── text_to_sql.py           # Agente LangGraph
│
├── sql/
│   └── 001_schema.sql               # 6 tabelas + índices
│
├── models/                          # artefatos joblib (gitignored)
│
├── scripts/
│   └── validate.py                  # smoke test E2E de 17 endpoints
│
└── reports/                         # CSV/HTML gerados (gitignored)
```

---

## 12. Validação automatizada e segurança

### `scripts/validate.py`

Smoke test E2E que testa **17 cenários** contra qualquer URL (`--base-url`):

| Categoria | Casos |
|-----------|-------|
| System | health |
| Auth | register, register duplicado (409), senha curta (422), login OK, login errado (401), /me sem token (401), /me com token |
| Analytics | portfolio, agencies |
| Predições | collection-success |
| LLM | explain (Groq), portfolio-summary (Groq), 3 perguntas text-to-SQL (LangGraph), SQL injection bloqueada |

Saída atual contra produção: **17/17 PASS**.

### Segurança implementada

| Camada | Mecanismo |
|--------|-----------|
| Transport | HTTPS (gerenciado pelo Code Engine) |
| Autenticação | JWT HS256 com expiração de 60 min |
| Senhas | bcrypt com salt aleatório |
| Validação de entrada | Pydantic v2 (rejeita malformações em 422) |
| SQL injection (LLM) | regex allow-list + injeção forçada de LIMIT |
| Container | usuário não-root |
| Segredos | Code Engine secret store + `from-env-file` |
| CORS | (a configurar conforme o front consumidor) |
| Rate limiting | nativo do IBM Code Engine via concurrency limit |

---

## 13. Decisões de projeto comentadas

**Por que arquitetura medalhão e não um único script?**
Separar bronze/silver/gold permite re-processar uma camada sem refazer as outras, isolar problemas (sujeira na bronze não contamina o silver), e dá contratos claros entre camadas. É o padrão usado em Databricks, Snowflake, BigQuery.

**Por que notebooks Jupyter e não scripts Python para o ETL?**
Notebooks são o formato natural para descoberta progressiva — o analista vê cada `df.head()` ao vivo. Em produção real, esses notebooks seriam executados via Papermill no GitHub Actions. Para o contexto acadêmico, manter como notebooks deixa explícito **o raciocínio** que levou a cada decisão.

**Por que UV e não pip?**
UV resolve dependências em paralelo (10× mais rápido), gera `uv.lock` determinístico (reprodutibilidade garantida) e suporta nativamente `dependency-groups` (separar deps de notebook das de runtime).

**Por que XGBoost para Modelo A e LightGBM para B?**
Ambos são gradient boosting de árvore. Para A, escolhemos XGBoost por interpretabilidade nativa (`feature_importances_` direta). Para B (100k linhas), LightGBM é mais rápido com `categorical_feature=` interno. Para C, voltamos ao XGBoost porque a feature `recuperacao_estimada` (proxy físico) tem interação fina com `parcelas_pagas` que XGBoost capta melhor.

**Por que Cox PH e não árvore de sobrevivência?**
Cox PH é o modelo canônico de sobrevivência e tem interpretação direta (hazard ratios). Random Survival Forests seriam alternativa, mas sem ganho claro neste dataset (C-index baixo é limitação dos dados, não do método).

**Por que LangGraph e não LangChain puro?**
LangChain encadeia funções (chains). LangGraph orquestra **grafos de estado** — cada nó é uma função pura que recebe e devolve estado tipado. Para o text-to-SQL, isso permite ramificações futuras (re-gerar SQL se falhou na validação) sem reescrever o fluxo.

**Por que Supabase Pooler (porta 6543) e não a conexão direta?**
O pooler (Supavisor) compartilha conexões — necessário em serverless (Code Engine pode escalar a 0 e subir múltiplas instâncias). A porta 5432 direta seria limitada a poucas conexões simultâneas.

**Por que JWT e não sessões?**
Stateless = serverless friendly. Não precisamos de armazenamento server-side de sessão; o token carrega o claim necessário. O trade-off (revogação) é aceitável para o tempo de expiração curto (60 min).

**Por que separar `src/api/` e `src/insights/`?**
Inversão de dependência: `routers/insights.py` chama `insights.explainer` mas `insights/*` não importa nada de `api/*`. Isso permite reusar `explainer.py` em batch jobs, CLI ou Streamlit sem dependência do FastAPI.

**Por que parquet em vez de manter tudo no Postgres?**
Parquet é ~3× menor que tabela Postgres + permite leitura colunar local sem rede. Para iteração de feature engineering, ler `data/gold/contract_features.parquet` é instantâneo. O Postgres é o ponto de verdade para a API online.

**Por que IBM Code Engine e não Render/Fly/Railway?**
Code Engine tem free tier real (sem cartão), suporta scale-to-zero (custo = 0 quando ocioso), HTTPS automático com domínio gerenciado, e secret store integrado. Render exige cartão; Fly tem cota baixa; Railway eliminou o free tier.

