"""Agente Text-to-SQL com LangGraph.

Workflow:
    [pergunta PT-BR] → generate_sql → validate_sql → execute_sql → format_answer

Estado tipado, nós puros, segurança: somente SELECT, LIMIT obrigatório, sem DML.
"""

import re
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.insights.llm import get_llm


SCHEMA_DESCRIPTION = """
Esquema do banco (Postgres):

contracts(
  id_contrato TEXT PK,
  nome_assessoria TEXT,        -- 'Acerta Crédito Integrado', 'Fênix Recuperação De Crédito', 'Nexus Mediação Financeira', 'Vértice Asset & Cobrança'
  data_envio DATE,
  dias_atraso INTEGER,
  valor_inadimplente NUMERIC,
  status_cobranca TEXT,        -- 'Em Aberto', 'Acordo Firmado', 'Insucesso', 'Ajuizado'
  score_risco NUMERIC,         -- 0..100
  regiao TEXT,                 -- 'Norte', 'Nordeste', 'Centro-Oeste', 'Sudeste', 'Sul'
  faixa_valor TEXT             -- 'baixo', 'medio', 'alto', 'muito_alto'
)

payments(
  id_pagamento TEXT PK,
  id_contrato TEXT FK,
  numero_parcela INTEGER,
  data_vencimento DATE,
  data_pagamento DATE,         -- NULL se não pago
  valor_parcela NUMERIC,
  valor_pago NUMERIC,
  forma_pagamento TEXT,        -- 'Boleto', 'Pix', 'Débito Automático'
  contemplado BOOLEAN
)

contract_features(
  id_contrato TEXT PK FK,
  taxa_adimplencia NUMERIC,    -- 0..1
  total_pago NUMERIC,
  parcelas_pagas INTEGER,
  parcelas_total INTEGER,
  media_dias_atraso NUMERIC,
  metodo_predominante TEXT
)
"""


SQL_GEN_SYSTEM = """Você é um gerador de SQL para Postgres.
Receba uma pergunta em português e devolva **apenas** uma query SQL válida, sem
markdown, sem explicação, sem ponto-e-vírgula no final. Regras:

1. APENAS SELECT — nunca INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/TRUNCATE.
2. SEMPRE inclua LIMIT 100 (ou menos se pedido).
3. Use os nomes EXATOS de colunas e tabelas do schema abaixo.
4. Para colunas textuais com acento, use os valores EXATOS mostrados em comentários.

""" + SCHEMA_DESCRIPTION


ANSWER_SYSTEM = """Você é um analista de cobrança. Responda a pergunta do usuário
em português, de forma clara e objetiva, usando os dados retornados pelo SQL.
Não invente números — só use os que estão no resultado. Máximo 2 parágrafos."""


# -------- State --------
class SQLState(TypedDict, total=False):
    question: str
    sql: str
    validation_error: str
    rows: list[dict]
    answer: str


# -------- Nodes --------
def generate_sql(state: SQLState) -> SQLState:
    llm = get_llm(temperature=0.0)
    resp = llm.invoke([
        SystemMessage(content=SQL_GEN_SYSTEM),
        HumanMessage(content=state["question"]),
    ])
    sql = resp.content.strip()
    sql = re.sub(r"^```(?:sql)?\s*|\s*```$", "", sql, flags=re.MULTILINE).strip()
    sql = sql.rstrip(";")
    return {"sql": sql}


_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|vacuum)\b",
    re.IGNORECASE,
)


def validate_sql(state: SQLState) -> SQLState:
    sql = state.get("sql", "")
    if not sql:
        return {"validation_error": "SQL vazio."}
    if _FORBIDDEN.search(sql):
        return {"validation_error": "SQL contém operação não permitida (somente SELECT)."}
    if not re.match(r"^\s*(with|select)\b", sql, re.IGNORECASE):
        return {"validation_error": "SQL não começa com SELECT/WITH."}
    if "limit" not in sql.lower():
        # injeta LIMIT 100 se não tiver
        sql = sql + " LIMIT 100"
        return {"sql": sql, "validation_error": ""}
    return {"validation_error": ""}


def execute_sql(engine: Engine):
    def _exec(state: SQLState) -> SQLState:
        if state.get("validation_error"):
            return {"rows": []}
        with engine.connect() as c:
            result = c.execute(text(state["sql"]))
            rows = [dict(r._mapping) for r in result.fetchmany(100)]
        # serializa tipos não-JSON (Decimal, datetime, date)
        out = []
        for r in rows:
            out.append({k: (str(v) if v is not None and not isinstance(v, (int, float, bool, str)) else v)
                        for k, v in r.items()})
        return {"rows": out}
    return _exec


def format_answer(state: SQLState) -> SQLState:
    if state.get("validation_error"):
        return {"answer": f"Não foi possível responder: {state['validation_error']}"}
    rows = state.get("rows", [])
    if not rows:
        return {"answer": "A consulta não retornou resultados."}
    llm = get_llm(temperature=0.2)
    preview = rows[:20]
    resp = llm.invoke([
        SystemMessage(content=ANSWER_SYSTEM),
        HumanMessage(content=(
            f"Pergunta: {state['question']}\n\n"
            f"SQL executado:\n{state['sql']}\n\n"
            f"Resultados (até 20 linhas):\n{preview}"
        )),
    ])
    return {"answer": resp.content.strip()}


# -------- Graph factory --------
def build_graph(engine: Engine):
    g = StateGraph(SQLState)
    g.add_node("generate_sql", generate_sql)
    g.add_node("validate_sql", validate_sql)
    g.add_node("execute_sql", execute_sql(engine))
    g.add_node("format_answer", format_answer)

    g.set_entry_point("generate_sql")
    g.add_edge("generate_sql", "validate_sql")
    g.add_edge("validate_sql", "execute_sql")
    g.add_edge("execute_sql", "format_answer")
    g.add_edge("format_answer", END)
    return g.compile()


def ask(engine: Engine, question: str) -> dict:
    graph = build_graph(engine)
    result = graph.invoke({"question": question})
    return {
        "question": question,
        "sql_generated": result.get("sql", ""),
        "validation_error": result.get("validation_error", ""),
        "row_count": len(result.get("rows", [])),
        "rows_preview": result.get("rows", [])[:10],
        "answer_pt": result.get("answer", ""),
    }
