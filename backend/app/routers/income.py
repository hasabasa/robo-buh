"""Роутер приёма дохода: загрузка банковской выписки → income_ledger."""

from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..core.database import get_pool
from ..ingestion.service import ingest_mt940

router = APIRouter()


@router.post("/upload/mt940")
async def upload_mt940(taxpayer_id: UUID = Form(...), file: UploadFile = File(...)):
    """Загрузка выписки MT940: парсит, классифицирует по КНП, кладёт в income_ledger."""
    raw = await file.read()
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        content = raw.decode("cp1251", errors="replace")  # часть РК-банков в cp1251
    try:
        return await ingest_mt940(taxpayer_id, content)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(422, f"Не удалось разобрать MT940: {e}")


@router.get("/review-queue")
async def review_queue(taxpayer_id: UUID):
    """Операции, требующие ручной сверки (классификатор не уверен, is_income=NULL)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, op_date, amount, payment_channel, knp, purpose_text, counterparty_bin_iin
            FROM income_ledger
            WHERE taxpayer_id=$1 AND is_income IS NULL
            ORDER BY op_date
            """,
            taxpayer_id,
        )
    return [dict(r) for r in rows]
