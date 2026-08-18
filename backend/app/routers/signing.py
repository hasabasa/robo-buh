"""Роутер подписи деклараций. Подписывает клиент (NCALayer), сервер верифицирует."""

from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..core.database import get_pool
from ..signing.service import DeclarationSigningService, SignatureRejected
from ..signing.ncanode import NCANodeError

router = APIRouter()
_service = DeclarationSigningService()


class SubmitSignatureRequest(BaseModel):
    signed_xml: str = Field(..., description="XML декларации, подписанный ЭЦП клиента через NCALayer (basicsSignXML)")


@router.get("/{declaration_id}/xml")
async def get_declaration_xml(declaration_id: UUID):
    """Отдаёт несформированный/сформированный XML декларации, который клиент подпишет локально."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT form_code, status, xml FROM declarations WHERE id=$1", declaration_id
        )
    if not row:
        raise HTTPException(404, "Декларация не найдена")
    if not row["xml"]:
        raise HTTPException(409, "XML ещё не сгенерирован (нужен расчёт и билд формы)")
    return {"form_code": row["form_code"], "status": row["status"], "xml": row["xml"]}


@router.post("/{declaration_id}/sign")
async def submit_signature(declaration_id: UUID, body: SubmitSignatureRequest):
    """Приём подписанного клиентом XML: верификация NCANode + фиксация подписи."""
    try:
        return await _service.submit_signature(declaration_id, body.signed_xml)
    except SignatureRejected as e:
        raise HTTPException(422, str(e))
    except NCANodeError as e:
        raise HTTPException(503, f"Сервис проверки подписи недоступен: {e}")
