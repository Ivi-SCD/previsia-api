"""Pydantic v2 schemas for API I/O."""

from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


# -------- Auth --------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = None


class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str | None = None
    role: str
    created_at: datetime | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


# -------- Analytics --------
class PortfolioKPIs(BaseModel):
    total_contratos: int
    total_inadimplente_brl: float
    score_risco_medio: float
    taxa_acordo: float
    taxa_insucesso: float
    taxa_em_aberto: float


class AgencyPerf(BaseModel):
    nome_assessoria: str
    casos: int
    taxa_sucesso: float
    score_medio: float


# -------- Predictions --------
class ContractFeatures(BaseModel):
    score_risco: float
    dias_atraso_inicial: int | None = None
    valor_inadimplente: float
    parcelas_total: int = 0
    parcelas_pagas: int = 0
    total_pago: float = 0.0
    taxa_adimplencia: float = 0.0
    media_dias_atraso: float = 0.0
    velocidade_pagamento: float = 0.0
    faixa_valor: str
    dias_atraso_bucket: str
    regiao: str
    nome_assessoria: str
    metodo_predominante: str = "Boleto"


class SuccessPrediction(BaseModel):
    score: float
    label: str
