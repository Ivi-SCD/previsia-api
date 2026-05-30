"""Analytics endpoints — leitura agregada do Supabase, protegidos por JWT."""

from typing import Annotated
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.db import get_db
from src.api.schemas import AgencyPerf, PortfolioKPIs
from src.api.security import get_current_user

router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=[Depends(get_current_user)])


@router.get("/portfolio", response_model=PortfolioKPIs)
def portfolio(db: Annotated[Session, Depends(get_db)]):
    row = db.execute(text("""
        SELECT
            COUNT(*)                                                     AS total_contratos,
            COALESCE(SUM(valor_inadimplente), 0)                          AS total_inadimplente_brl,
            COALESCE(AVG(score_risco), 0)                                 AS score_risco_medio,
            AVG((status_cobranca = 'Acordo Firmado')::int)                AS taxa_acordo,
            AVG((status_cobranca = 'Insucesso')::int)                     AS taxa_insucesso,
            AVG((status_cobranca = 'Em Aberto')::int)                     AS taxa_em_aberto
        FROM contracts
    """)).mappings().first()
    return PortfolioKPIs(**dict(row))


@router.get("/agencies", response_model=list[AgencyPerf])
def agencies(db: Annotated[Session, Depends(get_db)]):
    rows = db.execute(text("""
        SELECT
            nome_assessoria,
            COUNT(*)                                                AS casos,
            AVG((status_cobranca = 'Acordo Firmado')::int)          AS taxa_sucesso,
            AVG(score_risco)                                        AS score_medio
        FROM contracts
        WHERE status_cobranca IN ('Acordo Firmado', 'Insucesso')
        GROUP BY nome_assessoria
        ORDER BY taxa_sucesso DESC
    """)).mappings().all()
    return [AgencyPerf(**dict(r)) for r in rows]
