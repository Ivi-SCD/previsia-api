-- Previsia — Database Schema
-- Run once against Supabase: psql $DATABASE_URL -f sql/001_schema.sql

CREATE TABLE IF NOT EXISTS contracts (
    id_contrato          TEXT PRIMARY KEY,
    nome_assessoria      TEXT NOT NULL,
    data_envio           DATE NOT NULL,
    dias_atraso          INTEGER,
    valor_inadimplente   NUMERIC(14, 2),
    status_cobranca      TEXT NOT NULL,
    score_risco          NUMERIC(5, 2),
    regiao               TEXT,
    faixa_valor          TEXT,
    dias_atraso_bucket   TEXT,
    created_at           TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS payments (
    id_pagamento          TEXT PRIMARY KEY,
    id_contrato           TEXT NOT NULL REFERENCES contracts(id_contrato),
    numero_parcela        INTEGER NOT NULL,
    data_vencimento       DATE NOT NULL,
    data_pagamento        DATE,
    valor_parcela         NUMERIC(10, 2) NOT NULL,
    valor_pago            NUMERIC(10, 2),
    forma_pagamento       TEXT,
    contemplado           BOOLEAN,
    dias_atraso_pagamento INTEGER,
    pago_em_dia           BOOLEAN,
    created_at            TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_payments_contrato ON payments(id_contrato);
CREATE INDEX IF NOT EXISTS idx_payments_vencimento ON payments(data_vencimento);
CREATE INDEX IF NOT EXISTS idx_contracts_status ON contracts(status_cobranca);
CREATE INDEX IF NOT EXISTS idx_contracts_assessoria ON contracts(nome_assessoria);

CREATE TABLE IF NOT EXISTS contract_features (
    id_contrato          TEXT PRIMARY KEY REFERENCES contracts(id_contrato),
    total_pago           NUMERIC(14, 2),
    taxa_adimplencia     NUMERIC(7, 4),
    media_dias_atraso    NUMERIC(8, 2),
    metodo_predominante  TEXT,
    parcelas_total       INTEGER,
    parcelas_pagas       INTEGER,
    primeiro_pagamento   DATE,
    velocidade_pagamento NUMERIC(14, 4),
    score_risco          NUMERIC(5, 2),
    dias_atraso_inicial  INTEGER,
    valor_inadimplente   NUMERIC(14, 2),
    faixa_valor          TEXT,
    regiao               TEXT,
    nome_assessoria      TEXT,
    label_sucesso        BOOLEAN,
    updated_at           TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS predictions (
    id            BIGSERIAL PRIMARY KEY,
    id_contrato   TEXT,
    model_name    TEXT NOT NULL,
    model_version TEXT NOT NULL,
    score         NUMERIC(6, 4),
    label         TEXT,
    features_json JSONB,
    created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_predictions_contrato ON predictions(id_contrato);
CREATE INDEX IF NOT EXISTS idx_predictions_model ON predictions(model_name, model_version);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id         BIGSERIAL PRIMARY KEY,
    run_type   TEXT NOT NULL,
    status     TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at   TIMESTAMPTZ,
    rows_in    INTEGER,
    rows_out   INTEGER,
    error      TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id            BIGSERIAL PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name     TEXT,
    role          TEXT NOT NULL DEFAULT 'analyst',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
