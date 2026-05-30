"""Explainer de risco: fetch contrato → predição → contexto → Groq em PT-BR."""

from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.config import settings
from src.insights.llm import get_llm


SYSTEM_PROMPT = """Você é um analista sênior de cobrança de uma fintech brasileira.
Sua tarefa é explicar, em português claro e direto, a probabilidade de sucesso de
uma cobrança para um gestor não-técnico. Use no máximo 3 parágrafos curtos.
Sempre inclua: (1) a probabilidade em %, (2) os 3 principais fatores que pesaram
na decisão e (3) uma recomendação prática de ação.
"""


@lru_cache
def _load_model() -> dict:
    path: Path = settings.model_dir / "collection_success_v1.joblib"
    return joblib.load(path)


def fetch_contract_features(db: Session, id_contrato: str) -> dict | None:
    row = db.execute(
        text("""
            SELECT
                cf.id_contrato, cf.score_risco, cf.dias_atraso_inicial,
                cf.valor_inadimplente, cf.parcelas_total, cf.parcelas_pagas,
                cf.total_pago, cf.taxa_adimplencia, cf.media_dias_atraso,
                cf.velocidade_pagamento, cf.faixa_valor, cf.regiao,
                cf.nome_assessoria, cf.metodo_predominante,
                c.dias_atraso_bucket, c.status_cobranca
            FROM contract_features cf
            JOIN contracts c USING (id_contrato)
            WHERE cf.id_contrato = :id
        """),
        {"id": id_contrato},
    ).mappings().first()
    return dict(row) if row else None


def predict_and_top_factors(features: dict) -> tuple[float, list[tuple[str, float]]]:
    art = _load_model()

    def f(key, default=0.0):
        v = features.get(key)
        return float(v) if v is not None else default

    def s(key, default):
        v = features.get(key)
        return str(v) if v else default

    df = pd.DataFrame([{
        "score_risco": f("score_risco", 50.0),
        "dias_atraso_inicial": int(features.get("dias_atraso_inicial") or 0),
        "valor_inadimplente": f("valor_inadimplente"),
        "parcelas_total": int(features.get("parcelas_total") or 0),
        "parcelas_pagas": int(features.get("parcelas_pagas") or 0),
        "total_pago": f("total_pago"),
        "taxa_adimplencia": f("taxa_adimplencia"),
        "media_dias_atraso": f("media_dias_atraso"),
        "velocidade_pagamento": f("velocidade_pagamento"),
        "faixa_valor": s("faixa_valor", "medio"),
        "dias_atraso_bucket": s("dias_atraso_bucket", "30-90d"),
        "regiao": s("regiao", "Sudeste"),
        "nome_assessoria": s("nome_assessoria", "Acerta Crédito Integrado"),
        "metodo_predominante": s("metodo_predominante", "Boleto"),
    }])

    for c in art["numeric_features"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
    for c in art["categorical_features"]:
        df[c] = df[c].astype("category")
    df = df[art["numeric_features"] + art["categorical_features"]]

    score = float(art["model"].predict_proba(df)[0, 1])

    imp = pd.Series(
        art["model"].feature_importances_,
        index=art["numeric_features"] + art["categorical_features"],
    ).sort_values(ascending=False)
    top = [(name, float(imp[name])) for name in imp.index[:3]]
    return score, top


def explain_contract(db: Session, id_contrato: str) -> dict:
    feats = fetch_contract_features(db, id_contrato)
    if feats is None:
        return {"error": f"Contrato {id_contrato} não encontrado"}

    score, top_factors = predict_and_top_factors(feats)
    risk_level = (
        "ALTO" if score < 0.3 else
        "BAIXO" if score > 0.7 else "MÉDIO"
    )

    ctx = (
        f"Contrato: {id_contrato}\n"
        f"Probabilidade de Acordo Firmado: {score:.1%}\n"
        f"Nível de risco de insucesso: {risk_level}\n"
        f"Score interno: {feats.get('score_risco')}/100\n"
        f"Dias em atraso inicial: {feats.get('dias_atraso_inicial')}\n"
        f"Valor inadimplente: R$ {float(feats.get('valor_inadimplente') or 0):,.2f}\n"
        f"Região: {feats.get('regiao')} | Assessoria: {feats.get('nome_assessoria')}\n"
        f"Parcelas pagas: {feats.get('parcelas_pagas')}/{feats.get('parcelas_total')} "
        f"(taxa {float(feats.get('taxa_adimplencia') or 0):.0%})\n"
        f"Status atual: {feats.get('status_cobranca')}\n\n"
        f"Top fatores do modelo (importância): "
        + ", ".join(f"{n} ({i:.3f})" for n, i in top_factors)
    )

    llm = get_llm(temperature=0.3)
    resp = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"Contexto:\n{ctx}\n\nElabore a explicação."),
    ])

    return {
        "id_contrato": id_contrato,
        "score": score,
        "risk_level": risk_level,
        "top_factors": [{"feature": n, "importance": i} for n, i in top_factors],
        "explanation_pt": resp.content.strip(),
    }
