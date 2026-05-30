"""Narrativa executiva do portfólio: KPIs agregados → Groq → 2 parágrafos PT-BR."""

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.insights.llm import get_llm


SYSTEM_PROMPT = """Você é um analista de portfólio de cobrança.
Escreva uma narrativa executiva em português, 2 parágrafos curtos,
destacando: saúde geral da carteira, principais pontos de atenção e
sugestões de foco operacional. Tom: direto, baseado em números."""


def collect_kpis(db: Session) -> dict:
    portfolio = db.execute(text("""
        SELECT
            COUNT(*)                                            AS total_contratos,
            SUM(valor_inadimplente)                             AS total_brl,
            AVG(score_risco)                                    AS score_medio,
            AVG((status_cobranca = 'Acordo Firmado')::int)      AS taxa_acordo,
            AVG((status_cobranca = 'Insucesso')::int)           AS taxa_insucesso
        FROM contracts
    """)).mappings().first()

    top_region = db.execute(text("""
        SELECT regiao, COUNT(*) AS n, SUM(valor_inadimplente) AS brl
        FROM contracts
        GROUP BY regiao ORDER BY brl DESC LIMIT 1
    """)).mappings().first()

    best_agency = db.execute(text("""
        SELECT nome_assessoria,
               AVG((status_cobranca = 'Acordo Firmado')::int) AS taxa
        FROM contracts
        WHERE status_cobranca IN ('Acordo Firmado', 'Insucesso')
        GROUP BY nome_assessoria ORDER BY taxa DESC LIMIT 1
    """)).mappings().first()

    return {
        "portfolio": dict(portfolio),
        "top_region": dict(top_region),
        "best_agency": dict(best_agency),
    }


def generate_summary(db: Session) -> dict:
    kpis = collect_kpis(db)
    p = kpis["portfolio"]
    r = kpis["top_region"]
    a = kpis["best_agency"]

    ctx = (
        f"Total de contratos: {p['total_contratos']:,}\n"
        f"Valor inadimplente total: R$ {float(p['total_brl']):,.2f}\n"
        f"Score interno médio: {float(p['score_medio']):.1f}/100\n"
        f"Taxa de acordo: {float(p['taxa_acordo']):.1%}\n"
        f"Taxa de insucesso: {float(p['taxa_insucesso']):.1%}\n"
        f"Região com maior exposição: {r['regiao']} "
        f"({r['n']} contratos, R$ {float(r['brl']):,.2f})\n"
        f"Assessoria mais eficaz: {a['nome_assessoria']} "
        f"({float(a['taxa']):.1%} de acordo)"
    )

    llm = get_llm(temperature=0.4)
    resp = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"KPIs do portfólio:\n{ctx}\n\nElabore a narrativa."),
    ])

    return {
        "kpis": kpis,
        "narrative_pt": resp.content.strip(),
    }
