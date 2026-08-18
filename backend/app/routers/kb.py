"""Роутер базы знаний: индексация + «спроси бухгалтера»."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..rag.indexer import reindex_knowledge_base
from ..rag.service import ask

router = APIRouter()


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3)
    k: int = Field(5, ge=1, le=10)


@router.post("/reindex")
async def reindex():
    """Индексирует docs/knowledge/*.md в векторную базу (эмбеддинги text-1024)."""
    return await reindex_knowledge_base()


@router.post("/ask")
async def ask_endpoint(body: AskRequest):
    """«Спроси бухгалтера»: ответ по базе знаний РК с указанием источников."""
    return await ask(body.question, body.k)
