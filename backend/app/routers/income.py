"""Роутер приёма дохода: загрузка банковской выписки → income_ledger."""

from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ..core.database import get_pool
from ..ingestion.service import ingest_statement, ingest_esf, ingest_pdf_statement

router = APIRouter()


@router.post("/upload")
async def upload_statement(taxpayer_id: UUID = Form(...), file: UploadFile = File(...)):
    """Загрузка выписки (MT940 или 1CClientBankExchange): автодетект → классификация → income_ledger."""
    raw = await file.read()
    if raw[:5] == b"%PDF-":                        # PDF-выписка (Kaspi) — отдельный путь
        try:
            return await ingest_pdf_statement(taxpayer_id, raw)
        except ValueError as e:
            raise HTTPException(422, str(e))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(422, f"Не удалось разобрать PDF-выписку: {e}")
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        content = raw.decode("cp1251", errors="replace")  # 1С и часть РК-банков в cp1251
    try:
        return await ingest_statement(taxpayer_id, content)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(422, f"Не удалось разобрать выписку: {e}")


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


@router.get("/ledger")
async def ledger(taxpayer_id: UUID, limit: int = 200):
    """Книга операций налогоплательщика (последние N), с классификацией."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, op_date, amount, payment_channel, knp, purpose_text,
                   counterparty_name, is_income, status, source
            FROM income_ledger WHERE taxpayer_id=$1
            ORDER BY op_date DESC NULLS LAST, amount DESC
            LIMIT $2
            """, taxpayer_id, limit)
    return [dict(r) for r in rows]


class ReviewDecision(BaseModel):
    is_income: bool


@router.post("/review/{op_id}")
async def review_confirm(op_id: UUID, body: ReviewDecision):
    """Ручная сверка: человек решает доход/не-доход по операции из очереди."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE income_ledger
            SET is_income=$2, status='confirmed', classified_by='human', confidence=1.0
            WHERE id=$1 RETURNING id
            """, op_id, body.is_income)
    if not row:
        raise HTTPException(404, "Операция не найдена")
    return {"id": str(op_id), "is_income": body.is_income, "status": "confirmed"}


@router.post("/esf/upload")
async def upload_esf(taxpayer_id: UUID = Form(...), file: UploadFile = File(...)):
    """Загрузка выгрузки ЭСФ (invoiceContainer XML): счета → income_ledger с НДС."""
    raw = await file.read()
    try:
        return await ingest_esf(taxpayer_id, raw.decode("utf-8"))
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(422, f"Не удалось разобрать ЭСФ: {e}")
