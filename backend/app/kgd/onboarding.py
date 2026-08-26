"""Гейт онбординга и валидация налогоплательщика через справки КГД (Тир-1).

При заведении клиента: подтвердить, что БИН/ИИН реальный и действующий, вытащить УГД
(нужен для формы), проверить статус НДС. Валидация контрагентов из выписки — тем же клиентом.
"""

from __future__ import annotations

from .portal_client import KgdPortalClient, TaxpayerInfo


async def validate_taxpayer(code: str, kind: str = "too") -> dict:
    """Проверка клиента при онбординге. kind: 'too'→UL, 'ip'→IP."""
    tt = "UL" if kind == "too" else "IP"
    client = KgdPortalClient()
    info: TaxpayerInfo = await client.taxpayer(code, tt)

    if not info.found:
        return {"ok": False, "reason": "Налогоплательщик не найден в реестре КГД", "code": code}

    warnings = []
    if info.end_date:
        warnings.append(f"Внимание: снят с учёта/ликвидирован ({info.end_reason or info.end_date})")

    nds = await client.is_nds_payer(code)
    if nds:
        warnings.append("Клиент стоит на учёте по НДС — режим упрощёнки неприменим, нужен ОУР+НДС")

    return {
        "ok": True,
        "code": info.code,
        "name": info.name,
        "taxpayer_type": info.taxpayer_type,
        "begin_date": info.begin_date,
        "ugd_code": info.ugd_code,          # автозаполнение реквизита формы
        "ugd_name": info.ugd_name,
        "is_nds_payer": nds,
        "warnings": warnings,
    }
