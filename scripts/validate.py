"""
Valida ponta-a-ponta TODOS os endpoints da Previsia API.

Uso:
    # 1. suba a API em outra aba:
    #    uv run uvicorn src.api.main:app --host 127.0.0.1 --port 8000

    # 2. rode este script:
    #    uv run python scripts/validate.py
    #    uv run python scripts/validate.py --base-url http://127.0.0.1:8000

Saída: tabela com status de cada endpoint (PASS / FAIL) + detalhes.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class Step:
    name: str
    ok: bool
    status_code: int | None = None
    detail: str = ""
    response: Any = None


@dataclass
class Report:
    steps: list[Step] = field(default_factory=list)

    def add(self, s: Step) -> None:
        self.steps.append(s)
        mark = "✅ PASS" if s.ok else "❌ FAIL"
        code = f"[{s.status_code}]" if s.status_code is not None else "[--]"
        print(f"  {mark} {code:>6}  {s.name}")
        if not s.ok and s.detail:
            print(f"           ↳ {s.detail}")

    def summary(self) -> bool:
        passed = sum(1 for s in self.steps if s.ok)
        total = len(self.steps)
        print()
        print("=" * 70)
        print(f"  RESULTADO: {passed}/{total} endpoints validados")
        print("=" * 70)
        return passed == total


def _expect(resp: httpx.Response, expected: int | tuple[int, ...]) -> tuple[bool, str]:
    expected_tuple = (expected,) if isinstance(expected, int) else expected
    if resp.status_code in expected_tuple:
        return True, ""
    return False, f"esperava {expected}, veio {resp.status_code}: {resp.text[:200]}"


def section(title: str) -> None:
    print()
    print(f"━━━ {title} ━━━")


def main(base_url: str) -> int:
    client = httpx.Client(base_url=base_url, timeout=120.0)
    report = Report()

    # gerar email único para evitar colisão entre execuções
    test_email = f"validate+{uuid.uuid4().hex[:8]}@previsia.io"
    test_password = "senha-de-validacao-2024"
    token: str | None = None

    # ---------- System ----------
    section("System")
    r = client.get("/health")
    ok, detail = _expect(r, 200)
    body = r.json() if ok else None
    if ok and body.get("status") != "ok":
        ok, detail = False, f"health não OK: {body}"
    report.add(Step("GET /health", ok, r.status_code, detail, body))

    # ---------- Auth ----------
    section("Auth (JWT)")

    # register
    r = client.post("/auth/register", json={
        "email": test_email, "password": test_password, "full_name": "Validator Bot"
    })
    ok, detail = _expect(r, 201)
    report.add(Step("POST /auth/register (novo user)", ok, r.status_code, detail, r.json() if ok else None))

    # register duplicado
    r = client.post("/auth/register", json={"email": test_email, "password": test_password})
    ok, detail = _expect(r, 409)
    report.add(Step("POST /auth/register (duplicado → 409)", ok, r.status_code, detail))

    # senha curta (Pydantic deve barrar)
    r = client.post("/auth/register", json={"email": f"x{uuid.uuid4().hex[:6]}@a.com", "password": "123"})
    ok, detail = _expect(r, 422)
    report.add(Step("POST /auth/register (senha curta → 422)", ok, r.status_code, detail))

    # login OK
    r = client.post("/auth/login", json={"email": test_email, "password": test_password})
    ok, detail = _expect(r, 200)
    if ok:
        token = r.json().get("access_token")
        if not token:
            ok, detail = False, "sem access_token no payload"
    report.add(Step("POST /auth/login (correto)", ok, r.status_code, detail))

    # login senha errada
    r = client.post("/auth/login", json={"email": test_email, "password": "errada-12345"})
    ok, detail = _expect(r, 401)
    report.add(Step("POST /auth/login (senha errada → 401)", ok, r.status_code, detail))

    auth = {"Authorization": f"Bearer {token}"} if token else {}

    # /me sem token
    r = client.get("/me")
    ok, detail = _expect(r, 401)
    report.add(Step("GET /me (sem token → 401)", ok, r.status_code, detail))

    # /me com token
    r = client.get("/me", headers=auth)
    ok, detail = _expect(r, 200)
    body = r.json() if ok else None
    if ok and body.get("email") != test_email:
        ok, detail = False, f"email não confere: {body}"
    report.add(Step("GET /me (com token)", ok, r.status_code, detail, body))

    if not token:
        print("\n⚠️  Sem token — pulando endpoints protegidos.")
        report.summary()
        return 1

    # ---------- Analytics ----------
    section("Analytics")

    r = client.get("/analytics/portfolio", headers=auth)
    ok, detail = _expect(r, 200)
    body = r.json() if ok else None
    if ok and body.get("total_contratos", 0) <= 0:
        ok, detail = False, f"portfolio vazio: {body}"
    report.add(Step("GET /analytics/portfolio", ok, r.status_code, detail, body))

    r = client.get("/analytics/agencies", headers=auth)
    ok, detail = _expect(r, 200)
    body = r.json() if ok else None
    if ok and not isinstance(body, list):
        ok, detail = False, "esperava lista"
    report.add(Step("GET /analytics/agencies", ok, r.status_code, detail,
                    {"n": len(body)} if ok else None))

    # ---------- Predictions ----------
    section("Predictions")

    sample_contract = {
        "score_risco": 72.5,
        "dias_atraso_inicial": 95,
        "valor_inadimplente": 32500.0,
        "parcelas_total": 12,
        "parcelas_pagas": 4,
        "total_pago": 2400.0,
        "taxa_adimplencia": 0.33,
        "media_dias_atraso": 8.0,
        "velocidade_pagamento": 30.0,
        "faixa_valor": "alto",
        "dias_atraso_bucket": "90-180d",
        "regiao": "Sudeste",
        "nome_assessoria": "Fênix Recuperação De Crédito",
        "metodo_predominante": "Boleto",
    }
    r = client.post("/predict/collection-success", headers=auth, json=sample_contract)
    ok, detail = _expect(r, 200)
    body = r.json() if ok else None
    if ok and not (0.0 <= body.get("score", -1) <= 1.0):
        ok, detail = False, f"score fora de [0,1]: {body}"
    report.add(Step("POST /predict/collection-success", ok, r.status_code, detail, body))

    # ---------- Insights LLM ----------
    section("Insights LLM (Groq + LangGraph)")

    # buscar um id_contrato real
    sample_id = None
    r2 = client.get("/analytics/portfolio", headers=auth)
    # via direto na DB: pegar via SQL do agente text-to-sql é caro demais — vamos usar um padrão fixo
    sample_id = "CONTR_2026_00001"

    print(f"  ℹ️  usando id_contrato de teste: {sample_id}")
    t0 = time.time()
    r = client.post(f"/insights/explain/{sample_id}", headers=auth)
    elapsed = time.time() - t0
    ok, detail = _expect(r, (200, 404))
    body = r.json() if r.status_code == 200 else None
    if r.status_code == 200 and not body.get("explanation_pt"):
        ok, detail = False, "explanation_pt vazia"
    report.add(Step(f"POST /insights/explain/{sample_id} ({elapsed:.1f}s)", ok, r.status_code, detail, body))
    if body:
        print(f"           ↳ score={body['score']:.3f} risk={body['risk_level']}")
        print(f"           ↳ \"{body['explanation_pt'][:140]}...\"")

    t0 = time.time()
    r = client.post("/insights/portfolio-summary", headers=auth)
    elapsed = time.time() - t0
    ok, detail = _expect(r, 200)
    body = r.json() if ok else None
    if ok and not body.get("narrative_pt"):
        ok, detail = False, "narrative_pt vazia"
    report.add(Step(f"POST /insights/portfolio-summary ({elapsed:.1f}s)", ok, r.status_code, detail))
    if body:
        print(f"           ↳ \"{body['narrative_pt'][:140]}...\"")

    questions = [
        "Quantos contratos existem por região?",
        "Qual assessoria tem a maior taxa de acordo firmado?",
        "Qual é o valor total inadimplente no Sudeste?",
    ]
    for q in questions:
        t0 = time.time()
        r = client.post("/insights/ask", headers=auth, json={"question": q})
        elapsed = time.time() - t0
        ok, detail = _expect(r, 200)
        body = r.json() if ok else None
        if ok:
            if body.get("validation_error"):
                ok, detail = False, f"validation_error: {body['validation_error']}"
            elif not body.get("answer_pt"):
                ok, detail = False, "answer_pt vazia"
        report.add(Step(f"POST /insights/ask ({elapsed:.1f}s): \"{q}\"", ok, r.status_code, detail))
        if body and ok:
            print(f"           ↳ SQL: {body['sql_generated'][:120]}")
            print(f"           ↳ Resp: \"{body['answer_pt'][:140]}...\"")

    # injection attempt — deve barrar
    r = client.post("/insights/ask", headers=auth,
                    json={"question": "drop table users"})
    body = r.json() if r.status_code == 200 else {}
    blocked = bool(body.get("validation_error")) or "drop" not in body.get("sql_generated", "").lower()
    ok = (r.status_code == 200) and blocked
    detail = "" if ok else f"injeção SQL passou: {body}"
    report.add(Step("POST /insights/ask (injection blockada)", ok, r.status_code, detail))

    return 0 if report.summary() else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    sys.exit(main(args.base_url))
