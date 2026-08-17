"""CRUD налогоплательщиков — первая рабочая поверхность API."""

import json
from datetime import date
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from ..core.database import get_pool

router = APIRouter()


class TaxpayerCreate(BaseModel):
    user_id: UUID
    kind: str = Field(pattern="^(ip|too)$")
    iin_bin: str = Field(min_length=12, max_length=12)
    name: str
    oked: str | None = None
    ugd_code: str | None = None
    maslikhat_rate: float | None = Field(default=None, ge=2.0, le=6.0)
    birth_date: date | None = None
    kaspi_api_token: str | None = None

    @field_validator("iin_bin")
    @classmethod
    def digits_only(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("ИИН/БИН — ровно 12 цифр")
        return v


@router.post("", status_code=201)
async def create_taxpayer(body: TaxpayerCreate):
    pool = await get_pool()
    async with pool.acquire() as conn:
        # user создаём лениво, если бухгалтер ещё не заведён (упрощение прототипа)
        row = await conn.fetchrow(
            """
            INSERT INTO taxpayers
                (user_id, kind, iin_bin, name, oked, ugd_code,
                 maslikhat_rate, birth_date, kaspi_api_token)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
            ON CONFLICT (user_id, iin_bin) DO UPDATE SET
                name = EXCLUDED.name,
                oked = COALESCE(EXCLUDED.oked, taxpayers.oked),
                ugd_code = COALESCE(EXCLUDED.ugd_code, taxpayers.ugd_code),
                maslikhat_rate = COALESCE(EXCLUDED.maslikhat_rate, taxpayers.maslikhat_rate),
                birth_date = COALESCE(EXCLUDED.birth_date, taxpayers.birth_date),
                kaspi_api_token = COALESCE(EXCLUDED.kaspi_api_token, taxpayers.kaspi_api_token)
            RETURNING id, kind, iin_bin, name, tax_regime, created_at
            """,
            body.user_id, body.kind, body.iin_bin, body.name, body.oked,
            body.ugd_code, body.maslikhat_rate, body.birth_date, body.kaspi_api_token,
        )
    return dict(row)


@router.get("/{taxpayer_id}")
async def get_taxpayer(taxpayer_id: UUID):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, user_id, kind, iin_bin, name, tax_regime, oked, ugd_code,
                   maslikhat_rate, birth_date, requisites, created_at,
                   (kaspi_api_token IS NOT NULL) AS has_kaspi_token
            FROM taxpayers WHERE id = $1
            """,
            taxpayer_id,
        )
    if not row:
        raise HTTPException(404, "Налогоплательщик не найден")
    d = dict(row)
    d["requisites"] = json.loads(d["requisites"]) if isinstance(d["requisites"], str) else d["requisites"]
    return d


@router.get("")
async def list_taxpayers(user_id: UUID):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, kind, iin_bin, name, tax_regime, ugd_code, maslikhat_rate,
                   (kaspi_api_token IS NOT NULL) AS has_kaspi_token
            FROM taxpayers WHERE user_id = $1 ORDER BY created_at
            """,
            user_id,
        )
    return [dict(r) for r in rows]
