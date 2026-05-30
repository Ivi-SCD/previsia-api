"""FastAPI entrypoint."""

from fastapi import FastAPI
from sqlalchemy import text

from src.api.db import engine
from src.api.routers import analytics, auth, insights, me, predict


app = FastAPI(
    title="Previsia API",
    description="Plataforma de inteligência preditiva em cobrança de dívidas",
    version="0.1.0",
)


@app.get("/health", tags=["system"])
def health():
    try:
        with engine.connect() as c:
            ok = c.execute(text("select 1")).scalar() == 1
    except Exception as e:
        return {"status": "degraded", "db": str(e)}
    return {"status": "ok", "db": ok}


app.include_router(auth.router)
app.include_router(me.router)
app.include_router(analytics.router)
app.include_router(predict.router)
app.include_router(insights.router)
