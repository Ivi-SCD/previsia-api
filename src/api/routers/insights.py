"""Endpoints de insights LLM (Groq + LangGraph)."""

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.db import engine, get_db
from src.api.security import get_current_user
from src.insights.explainer import explain_contract
from src.insights.portfolio_summary import generate_summary
from src.insights.text_to_sql import ask


router = APIRouter(prefix="/insights", tags=["insights"], dependencies=[Depends(get_current_user)])


class AskIn(BaseModel):
    question: str


@router.post("/explain/{id_contrato}")
def explain(id_contrato: str, db: Annotated[Session, Depends(get_db)]):
    result = explain_contract(db, id_contrato)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@router.post("/portfolio-summary")
def portfolio_summary(db: Annotated[Session, Depends(get_db)]):
    return generate_summary(db)


@router.post("/ask")
def ask_endpoint(payload: AskIn):
    if not payload.question.strip():
        raise HTTPException(400, "Pergunta vazia")
    return ask(engine, payload.question)
