"""Подпись декларации ЭЦП: приём подписанного клиентом XML → верификация → аудит.

Юридически чисто: клиент подписывает XML СВОЕЙ ЭЦП локально (NCALayer), сервер только
проверяет через NCANode и фиксирует, кто подписал. Приватный ключ сюда не попадает.
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

from ..core.database import get_pool
from .ncanode import NCANodeClient, SignerInfo

logger = logging.getLogger(__name__)


class SignatureRejected(Exception):
    """Подпись отклонена (невалидна, чужой БИН, декларация не в том статусе)."""


class DeclarationSigningService:
    def __init__(self, ncanode: NCANodeClient | None = None):
        self.ncanode = ncanode or NCANodeClient()

    async def submit_signature(self, declaration_id: UUID, signed_xml: str) -> dict:
        """Принимает подписанный клиентом XML декларации, верифицирует, фиксирует подпись."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            decl = await conn.fetchrow(
                "SELECT id, taxpayer_id, form_code, status FROM declarations WHERE id=$1",
                declaration_id,
            )
            if not decl:
                raise SignatureRejected("Декларация не найдена")
            if decl["status"] not in ("draft", "confirmed"):
                raise SignatureRejected(f"Декларация уже в статусе '{decl['status']}', подпись не принимается")
            taxpayer = await conn.fetchrow(
                "SELECT iin_bin, kind FROM taxpayers WHERE id=$1", decl["taxpayer_id"]
            )

        # 1. Верификация подписи через NCANode
        signers = await self.ncanode.verify_xml(signed_xml)
        if not signers:
            raise SignatureRejected("В XML нет подписей")
        signer = signers[0]

        # 2. Подпись должна быть валидной (в проде — цепочка НУЦ; revocationCheck на боевом)
        if not signer.valid:
            raise SignatureRejected("Подпись невалидна (сертификат вне доверенной цепочки НУЦ или отозван)")

        # 3. Сверка: подписант = сам налогоплательщик (БИН/ИИН в сертификате = БИН/ИИН декларации)
        self._check_signer_matches_taxpayer(signer, taxpayer)

        # 4. Фиксируем подпись + переводим декларацию в signed
        async with pool.acquire() as conn:
            async with conn.transaction():
                sig_id = await conn.fetchval(
                    """
                    INSERT INTO document_signatures
                        (declaration_id, signer_iin, signer_bin, signer_name,
                         signature_kind, signature, certificate_serial,
                         certificate_not_before, certificate_not_after, certificate_issuer,
                         verified, verification_details)
                    VALUES ($1,$2,$3,$4,'xmldsig',$5,$6,$7,$8,$9,$10,$11)
                    RETURNING id
                    """,
                    declaration_id, signer.iin, signer.bin, signer.signer_name,
                    signed_xml, signer.serial_number, signer.not_before, signer.not_after,
                    signer.issuer, signer.valid, json.dumps(signer.raw, default=str),
                )
                await conn.execute(
                    "UPDATE declarations SET xml=$2, status='signed', updated_at=now() WHERE id=$1",
                    declaration_id, signed_xml,
                )
        logger.info("Декларация %s подписана (ИИН/БИН %s/%s, sig=%s)",
                    declaration_id, signer.iin, signer.bin, sig_id)
        return {
            "declaration_id": str(declaration_id),
            "status": "signed",
            "signature_id": str(sig_id),
            "signer": {"iin": signer.iin, "bin": signer.bin, "name": signer.signer_name},
        }

    @staticmethod
    def _check_signer_matches_taxpayer(signer: SignerInfo, taxpayer) -> None:
        if not taxpayer:
            return  # налогоплательщик мог быть удалён — не блокируем аудит подписи
        want = taxpayer["iin_bin"]
        got = signer.bin or signer.iin
        if got and got != want:
            raise SignatureRejected(
                f"Подпись чужая: в сертификате {got}, декларация на {want}. "
                f"Декларацию подписывает сам налогоплательщик."
            )
