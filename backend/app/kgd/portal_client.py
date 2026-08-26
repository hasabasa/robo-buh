"""Клиент справочных REST-сервисов КГД (портал ИСНА, Тир-1: оператор-токен X-Portal-Token).

База и заголовок из config. Публичные справки по ИИН/БИН: статус налогоплательщика,
регистрация НДС, ликвидация. Приватные (долги) требуют personalAccountToken клиента — не тут.
Сверено вживую 26.08.2026 на БИН 260440029440.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from ..config import settings

logger = logging.getLogger(__name__)


class KgdPortalError(RuntimeError):
    pass


@dataclass
class TaxpayerInfo:
    found: bool
    code: str | None
    taxpayer_type: str | None       # UL | IP | LZCHP
    name: str | None
    begin_date: str | None
    end_date: str | None            # заполнен → ликвидирован/снят
    end_reason: str | None
    ugd_code: str | None            # код УГД (для формы!)
    ugd_name: str | None
    is_nds_payer: bool | None       # None = не проверяли
    raw: dict


class KgdPortalClient:
    def __init__(self, token: str | None = None, base: str | None = None, timeout: float = 25.0):
        self.token = token or settings.kgd_portal_token
        self.base = (base or settings.kgd_portal_base).rstrip("/")
        self.timeout = timeout

    def _headers(self) -> dict:
        if not self.token:
            raise KgdPortalError("Не задан KGD_PORTAL_TOKEN")
        return {"X-Portal-Token": self.token, "Accept": "application/json",
                "User-Agent": "Mozilla/5.0"}

    async def _get(self, path: str, params: dict) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as c:
            try:
                r = await c.get(f"{self.base}{path}", params=params, headers=self._headers())
            except httpx.RequestError as e:
                raise KgdPortalError(f"КГД {path} недоступен: {e}")
        if r.status_code >= 500:
            raise KgdPortalError(f"КГД {path}: HTTP {r.status_code} {r.text[:160]}")
        try:
            return r.json()
        except ValueError:
            return {}

    async def taxpayer(self, code: str, taxpayer_type: str = "UL", name: str = "") -> TaxpayerInfo:
        """Поиск налогоплательщика (taxpayer-data). taxpayer_type: UL|IP|LZCHP."""
        params = {"taxpayerCode": code, "taxpayerType": taxpayer_type}
        if name:
            params["name"] = name
        data = await self._get("/taxpayer-data", params)
        resp = (data.get("taxpayerPortalSearchResponses") or [{}])[0]
        pay = data.get("paymentAnswer") or {}
        first_pay = (pay.get("payment") or [{}])[0] if pay.get("payment") else {}
        er = resp.get("endReason") or {}
        return TaxpayerInfo(
            found=resp.get("messageResult") == "SUCCESS",
            code=resp.get("code"),
            taxpayer_type=resp.get("taxpayerType"),
            name=resp.get("name"),
            begin_date=resp.get("beginDate"),
            end_date=resp.get("endDate"),
            end_reason=er.get("ru") if isinstance(er, dict) else None,
            ugd_code=first_pay.get("taxOrgCode"),
            ugd_name=first_pay.get("nameTaxRu"),
            is_nds_payer=None,
            raw=data,
        )

    async def is_nds_payer(self, code: str) -> bool | None:
        """Стоит ли на учёте по НДС (search-payer-data). None если ответ пустой/неясный."""
        data = await self._get("/search-payer-data", {"taxpayerCode": code})
        if not data:
            return False
        # непустой ответ с данными свидетельства = плательщик НДС
        return bool(data.get("ndsRegistrationDate") or data.get("content") or data.get("data"))
