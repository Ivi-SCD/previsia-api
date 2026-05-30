"""Auth endpoints: /auth/register and /auth/login."""

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.db import get_db
from src.api.schemas import RegisterIn, TokenOut, UserOut
from src.api.security import hash_password, verify_password, create_access_token


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(payload: RegisterIn, db: Annotated[Session, Depends(get_db)]):
    exists = db.execute(
        text("SELECT 1 FROM users WHERE email = :e"), {"e": payload.email}
    ).first()
    if exists:
        raise HTTPException(status_code=409, detail="Email já cadastrado")

    row = db.execute(
        text("""
            INSERT INTO users (email, password_hash, full_name)
            VALUES (:e, :p, :n)
            RETURNING id, email, full_name, role, created_at
        """),
        {
            "e": payload.email,
            "p": hash_password(payload.password),
            "n": payload.full_name,
        },
    ).mappings().first()
    db.commit()
    return UserOut(**dict(row))


@router.post("/login", response_model=TokenOut)
def login(payload: RegisterIn, db: Annotated[Session, Depends(get_db)]):
    row = db.execute(
        text("SELECT id, email, password_hash FROM users WHERE email = :e"),
        {"e": payload.email},
    ).mappings().first()
    if row is None or not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha inválidos",
        )
    token = create_access_token(subject=row["email"], extra={"uid": row["id"]})
    return TokenOut(access_token=token)
