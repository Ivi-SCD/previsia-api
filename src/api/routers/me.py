"""Endpoint protegido: /me — devolve o user do token."""

from typing import Annotated
from fastapi import APIRouter, Depends

from src.api.schemas import UserOut
from src.api.security import get_current_user

router = APIRouter(tags=["me"])


@router.get("/me", response_model=UserOut)
def me(user: Annotated[dict, Depends(get_current_user)]):
    return UserOut(**user)
