"""Клиент NCANode v3 — верификация подписей ЭЦП НУЦ РК.

Сервер НИЧЕГО не подписывает боевыми ключами: клиент подписывает XML своей ЭЦП
локально (NCALayer, basicsSignXML), сюда приходит уже подписанный XML на проверку.
Метод sign_xml используется ТОЛЬКО в тест-харнессе (тестовый сертификат).

API сверен вживую по /v3/api-docs запущенного malikzh/ncanode:
  POST /xml/verify   {xml, revocationCheck:[]} → {valid, signers:[{...}]}
  POST /xml/sign     {xml, signers:[{key,password}]} → {status, xml}   (только тесты)
  POST /pkcs12/info  {keys:[{key,password}], revocationCheck:[]}
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class SignerInfo:
    valid: bool
    iin: str | None
    bin: str | None
    signer_name: str | None
    org: str | None
    serial_number: str | None
    not_before: datetime | None
    not_after: datetime | None
    issuer: str | None
    raw: dict[str, Any]


class NCANodeError(RuntimeError):
    pass


class NCANodeClient:
    def __init__(self, base_url: str | None = None, timeout: float = 30.0):
        self.base_url = (base_url or settings.ncanode_url).rstrip("/")
        self.timeout = timeout

    async def _post(self, path: str, body: dict) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as c:
            try:
                r = await c.post(f"{self.base_url}{path}", json=body)
                r.raise_for_status()
                return r.json()
            except httpx.HTTPStatusError as e:
                raise NCANodeError(f"NCANode {path}: HTTP {e.response.status_code} {e.response.text[:200]}")
            except httpx.RequestError as e:
                raise NCANodeError(f"NCANode {path} недоступен: {e}")

    async def verify_xml(self, signed_xml: str, *, revocation_check: list[str] | None = None) -> list[SignerInfo]:
        """Проверяет подписанный XML, возвращает список подписантов с извлечёнными ИИН/БИН."""
        data = await self._post("/xml/verify", {
            "xml": signed_xml,
            "revocationCheck": revocation_check or [],
        })
        signers = data.get("signers") or []
        return [self._parse_signer(s) for s in signers]

    async def sign_xml(self, xml: str, key_b64: str, password: str) -> str:
        """⚠️ ТОЛЬКО тест-харнесс: подписывает XML тестовым p12. Боевые ключи сюда не идут."""
        data = await self._post("/xml/sign", {
            "xml": xml,
            "signers": [{"key": key_b64, "password": password}],
        })
        signed = data.get("xml")
        if not signed:
            raise NCANodeError(f"xml/sign без результата: status={data.get('status')} msg={data.get('message')}")
        return signed

    @staticmethod
    def _parse_signer(s: dict) -> SignerInfo:
        subject = s.get("subject") or {}
        # ИИН/БИН НУЦ кладёт в serialNumber субъекта как IIN.../BIN...; подстрахуемся полями signer-уровня
        serial_number_field = str(
            subject.get("serialNumber") or s.get("keyUser") or s.get("serialNumber") or ""
        )
        iin = bin_ = None
        up = serial_number_field.upper()
        if "IIN" in up:
            iin = up.split("IIN", 1)[1][:12]
        if "BIN" in up:
            bin_ = up.split("BIN", 1)[1][:12]
        return SignerInfo(
            valid=bool(s.get("valid")),
            iin=iin if (iin and iin.isdigit()) else None,
            bin=bin_ if (bin_ and bin_.isdigit()) else None,
            signer_name=subject.get("commonName") or subject.get("cn") or s.get("keyUser"),
            org=subject.get("organization") or subject.get("o"),
            serial_number=s.get("serialNumber") or subject.get("serialNumber"),
            not_before=_parse_dt(s.get("notBefore")),
            not_after=_parse_dt(s.get("notAfter")),
            issuer=(s.get("issuer") or {}).get("commonName") if isinstance(s.get("issuer"), dict) else s.get("issuer"),
            raw=s,
        )


def _parse_dt(v) -> datetime | None:
    if not v:
        return None
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y"):
        try:
            return datetime.strptime(str(v)[:19], fmt)
        except (ValueError, TypeError):
            continue
    return None
