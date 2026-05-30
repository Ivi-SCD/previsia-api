"""Cliente Groq via LangChain. Centralizado pra ficar fácil trocar o modelo."""

from langchain_groq import ChatGroq
from src.config import settings


def get_llm(temperature: float = 0.2) -> ChatGroq:
    return ChatGroq(
        api_key=settings.groq_api_key,
        model="llama-3.3-70b-versatile",
        temperature=temperature,
    )
