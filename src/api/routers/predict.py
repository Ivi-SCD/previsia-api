"""Endpoint de inferência: /predict/collection-success (Modelo A)."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

import joblib
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

from src.api.schemas import ContractFeatures, SuccessPrediction
from src.api.security import get_current_user
from src.config import settings

router = APIRouter(prefix="/predict", tags=["predict"], dependencies=[Depends(get_current_user)])


@lru_cache
def _load(name: str) -> dict:
    path: Path = settings.model_dir / name
    if not path.exists():
        raise HTTPException(503, f"Modelo não disponível: {path}")
    return joblib.load(path)


@router.post("/collection-success", response_model=SuccessPrediction)
def collection_success(payload: ContractFeatures):
    art = _load("collection_success_v1.joblib")
    df = pd.DataFrame([payload.model_dump()])

    for c in art["categorical_features"]:
        df[c] = df[c].astype("category")
    df = df[art["numeric_features"] + art["categorical_features"]]

    score = float(art["model"].predict_proba(df)[0, 1])
    label = "Acordo Firmado" if score >= 0.5 else "Insucesso"
    return SuccessPrediction(score=score, label=label)
