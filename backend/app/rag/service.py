"""«Спроси бухгалтера»: RAG по базе знаний РК.

Вопрос → эмбеддинг (text-1024) → косинус-поиск top-k чанков в kb_chunks → qwen3-6
отвечает СТРОГО по найденным фрагментам (не выдумывает). Векторы нормализованы, поэтому
косинус = скалярное произведение.
"""

from __future__ import annotations

import json
import logging

from ..config import settings
from ..core.database import get_pool
from ..ingestion.alem_client import AlemClient, AlemProvider

logger = logging.getLogger(__name__)

SYSTEM = (
    "Ты — ассистент по налогам и бухучёту Казахстана для сервиса robo-buh. Отвечай КРАТКО и "
    "ТОЛЬКО на основе приведённых фрагментов базы знаний. Если ответа в них нет — так и скажи, "
    "не выдумывай. Указывай числа/ставки/сроки как в источнике. В конце — список источников."
)


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))  # оба нормализованы → dot = cos


async def _embed_query(client: AlemClient, q: str) -> list[float]:
    return (await client.embed([q], model=settings.alem_embed_model,
                               api_key=settings.alem_embed_key))[0]


async def retrieve(question: str, k: int = 5) -> list[dict]:
    """Top-k релевантных чанков базы знаний по косинусу."""
    embed_client = AlemClient([AlemProvider(model=settings.alem_embed_model,
                                            api_key=settings.alem_embed_key,
                                            base_url=settings.alem_base_url)])
    try:
        qv = await _embed_query(embed_client, question)
    finally:
        await embed_client.close()

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT doc, heading, chunk_text, embedding FROM kb_chunks")
    scored = []
    for r in rows:
        vec = r["embedding"] if isinstance(r["embedding"], list) else json.loads(r["embedding"])
        scored.append((_cosine(qv, vec), r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"score": round(s, 4), "doc": r["doc"], "heading": r["heading"],
             "text": r["chunk_text"]} for s, r in scored[:k]]


async def ask(question: str, k: int = 5) -> dict:
    """Полный RAG-ответ: retrieve → qwen3-6 отвечает по контексту со ссылками."""
    hits = await retrieve(question, k)
    if not hits:
        return {"answer": "База знаний пуста — запустите индексацию (/api/kb/reindex).",
                "sources": []}

    context = "\n\n".join(
        f"[{h['doc']} · {h['heading']}]\n{h['text']}" for h in hits)
    llm = AlemClient([AlemProvider(model=settings.alem_vision_model,  # qwen3-6 (текстовый режим)
                                   api_key=settings.alem_vision_key,
                                   base_url=settings.alem_base_url, max_tokens=1500,
                                   disable_thinking=True)])
    try:
        resp = await llm.chat(SYSTEM, f"Вопрос: {question}\n\nФрагменты базы знаний:\n{context}")
    finally:
        await llm.close()

    return {
        "answer": resp.content,
        "sources": [{"doc": h["doc"], "heading": h["heading"], "score": h["score"]} for h in hits],
    }
