"""Индексация базы знаний: docs/knowledge/*.md → чанки → эмбеддинги (text-1024) → kb_chunks.

Чанкуем по markdown-заголовкам (### термин / ## раздел) — так каждый чанк = один термин
или раздел, что идеально для RAG по глоссарию. Идемпотентно по (doc, content_hash).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

from ..config import settings
from ..core.database import get_pool
from ..ingestion.alem_client import AlemClient, AlemProvider

logger = logging.getLogger(__name__)

_HEADING = re.compile(r"^#{2,4}\s+(.+)$", re.MULTILINE)


def _chunk_markdown(text: str) -> list[tuple[str, str]]:
    """Разбивает markdown на (заголовок, текст-чанк) по заголовкам 2–4 уровня."""
    matches = list(_HEADING.finditer(text))
    if not matches:
        return [("", text.strip())] if text.strip() else []
    chunks = []
    for i, m in enumerate(matches):
        heading = m.group(1).strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if len(body) > 20:
            chunks.append((heading, body))
    return chunks


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:16]


async def reindex_knowledge_base() -> dict:
    """Читает все .md из kb_docs_path, эмбеддит новые чанки, кладёт в kb_chunks."""
    docs_dir = Path(settings.kb_docs_path)
    files = sorted(docs_dir.glob("*.md")) if docs_dir.exists() else []
    if not files:
        return {"files": 0, "chunks_indexed": 0, "note": f"нет .md в {docs_dir}"}

    client = AlemClient([AlemProvider(model=settings.alem_embed_model,
                                      api_key=settings.alem_embed_key,
                                      base_url=settings.alem_base_url)])
    pool = await get_pool()
    indexed = 0
    try:
        async with pool.acquire() as conn:
            for f in files:
                for heading, body in _chunk_markdown(f.read_text(encoding="utf-8")):
                    h = _hash(body)
                    exists = await conn.fetchval(
                        "SELECT 1 FROM kb_chunks WHERE doc=$1 AND content_hash=$2", f.name, h)
                    if exists:
                        continue
                    vec = (await client.embed([body], model=settings.alem_embed_model,
                                              api_key=settings.alem_embed_key))[0]
                    await conn.execute(
                        "INSERT INTO kb_chunks (doc, heading, chunk_text, embedding, content_hash) "
                        "VALUES ($1,$2,$3,$4,$5) ON CONFLICT (doc, content_hash) DO NOTHING",
                        f.name, heading, body, json.dumps(vec), h)
                    indexed += 1
    finally:
        await client.close()

    logger.info("RAG reindex: файлов %d, новых чанков %d", len(files), indexed)
    return {"files": len(files), "chunks_indexed": indexed}
