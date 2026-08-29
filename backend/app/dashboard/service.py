"""Агрегатор дашборда: «сколько должен по всем налогам + что не сходится».

Один запрос собирает по налогоплательщику всю налоговую картину текущего цикла: применимые
налоги (по режиму) с суммами и сроками, светофор лимита СНР, долги/пеню и список проблем
(что мешает сдать: неразобранные операции, нет данных за период, приближение к лимиту).

Переиспользует движки (`compute_declaration_910`, `compute_vat_300`, `compute_200`,
`compute_kpn_100`) — единый источник правды. Читает «здесь и сейчас», ничего не кэширует.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from uuid import UUID

from ..core.database import get_pool
from .periods import current_half, current_quarter, due_dates_910, due_dates_200, next_social_due
from ..tax.service import compute_declaration_910
from ..tax.vat_service import compute_vat_300
from ..tax.payroll_service import compute_200
from ..tax.kpn_service import compute_kpn_100

logger = logging.getLogger(__name__)


def _d(x) -> Decimal:
    return Decimal(str(x or 0))


def _plural_ops(n: int) -> str:
    """Русское склонение: 1 операция, 2 операции, 5 операций."""
    tail = n % 100
    if 11 <= tail <= 14:
        w = "операций"
    else:
        d = n % 10
        w = "операция" if d == 1 else "операции" if 2 <= d <= 4 else "операций"
    return f"{n} {w}"


async def build_dashboard(taxpayer_id: UUID, today: date | None = None) -> dict:
    """Собирает дашборд налогоплательщика на дату `today` (по умолчанию — сегодня)."""
    today = today or date.today()
    year = today.year
    pool = await get_pool()
    async with pool.acquire() as conn:
        tp = await conn.fetchrow(
            "SELECT id, kind, name, tax_regime, iin_bin, birth_date, oked, ugd_code, requisites "
            "FROM taxpayers WHERE id=$1", taxpayer_id)
        if not tp:
            raise ValueError("Налогоплательщик не найден")
        n_employees = await conn.fetchval(
            "SELECT count(*) FROM employees WHERE taxpayer_id=$1 "
            "AND (fired_at IS NULL OR fired_at >= $2)", taxpayer_id, date(year, 1, 1)) or 0
        review_queue = await conn.fetchval(
            "SELECT count(*) FROM income_ledger WHERE taxpayer_id=$1 AND is_income IS NULL",
            taxpayer_id) or 0
        ops_this_year = await conn.fetchval(
            "SELECT count(*) FROM income_ledger WHERE taxpayer_id=$1 AND op_date >= $2",
            taxpayer_id, date(year, 1, 1)) or 0
        debt = await conn.fetchrow(
            "SELECT total_debt, penalty, has_bank_arrest FROM debt_snapshots "
            "WHERE taxpayer_id=$1 ORDER BY fetched_at DESC LIMIT 1", taxpayer_id)

    taxes: list[dict] = []
    snr = None

    if tp["tax_regime"] == "snr_simplified":
        half = current_half(today)
        d910 = await compute_declaration_910(taxpayer_id, year, half)
        submit, pay = due_dates_910(year, half)
        overdue = today > pay
        taxes.append({
            "code": "910.00", "label": d910["income_tax_name"], "period": d910["period"],
            "amount": _d(d910["income_tax"]), "due": pay.isoformat(),
            "kind": "к уплате" if overdue else "прогноз",
            "tone": "danger" if overdue else "brand",
            "hint": f"сдать до {submit.strftime('%d.%m.%Y')}, уплатить до {pay.strftime('%d.%m.%Y')}",
        })
        social = d910.get("social") or {}
        if social:
            due = next_social_due(today)
            taxes.append({
                "code": "social", "label": "Соцплатежи ИП (за месяц)", "period": due.strftime("%m.%Y"),
                "amount": _d(social["monthly"]["total"]), "due": due.isoformat(),
                "kind": "ежемесячно", "tone": "warn",
                "hint": "ОПВ + ОПВР + СО + ВОСМС · до 25 числа",
            })
        snr = d910.get("snr_limit")

    else:  # ОУР
        q = current_quarter(today)
        try:
            d300 = await compute_vat_300(taxpayer_id, year, q)
            if _d(d300["vat_payable"]) > 0:
                submit, pay = due_dates_200(year, q)  # 300 сдаётся в те же сроки, что 200
                taxes.append({
                    "code": "300.00", "label": "НДС к уплате", "period": d300["period"],
                    "amount": _d(d300["vat_payable"]), "due": pay.isoformat(),
                    "kind": "к уплате" if today > pay else "прогноз",
                    "tone": "danger" if today > pay else "brand",
                    "hint": f"квартал · уплатить до {pay.strftime('%d.%m.%Y')}",
                })
        except Exception as e:  # noqa: BLE001
            logger.warning("300.00 для дашборда: %s", e)
        d100 = await compute_kpn_100(taxpayer_id, year)
        if _d(d100.get("kpn", 0)) > 0:
            taxes.append({
                "code": "100.00", "label": "КПН (годовой, прогноз)", "period": str(year),
                "amount": _d(d100["kpn"]), "due": date(year + 1, 3, 31).isoformat(),
                "kind": "прогноз", "tone": "brand", "hint": "уплата до 10.04 след. года",
            })

    if n_employees > 0:
        q = current_quarter(today)
        d200 = await compute_200(taxpayer_id, year, q)
        if _d(d200.get("total_to_budget", 0)) > 0:
            submit, pay = due_dates_200(year, q)
            taxes.append({
                "code": "200.00", "label": "Зарплатные налоги (200.00)", "period": d200["period"],
                "amount": _d(d200["total_to_budget"]), "due": pay.isoformat(),
                "kind": "к уплате" if today > pay else "прогноз",
                "tone": "danger" if today > pay else "brand",
                "hint": f"{n_employees} работник(ов) · до {pay.strftime('%d.%m.%Y')}",
            })

    total_due = sum((t["amount"] for t in taxes), Decimal(0))
    debt_total = _d(debt["total_debt"]) if debt else Decimal(0)
    penalty = _d(debt["penalty"]) if debt else Decimal(0)

    # --- что не сходится ---
    issues: list[dict] = []
    if review_queue:
        issues.append({"tone": "warn", "title": f"{_plural_ops(review_queue)} на сверке",
                       "text": "Классификатор не уверен: доход это или нет. Пока не подтвердите — в оборот не идут."})
    if ops_this_year == 0:
        issues.append({"tone": "warn", "title": "Нет данных за год",
                       "text": "Не загружено ни одной операции — расчёт налога построен на пустом обороте."})
    if snr and snr.get("zone") not in ("green", "ok", None):
        issues.append({"tone": "danger" if snr["zone"] == "red" else "warn", "title": "Лимит СНР",
                       "text": snr.get("message", "Приближение к лимиту упрощёнки.")})
    if debt_total > 0:
        arrest = debt and debt["has_bank_arrest"]
        issues.append({"tone": "danger", "title": "Задолженность по КГД",
                       "text": ("Есть арест счёта. " if arrest else "") + "Пеня растёт ежедневно."})
    elif debt is None:
        issues.append({"tone": "warn", "title": "Долги/пени не проверены",
                       "text": "Задолженность по ИПН/ОСМС/соцотчислениям требует входа по ЭЦП в "
                               "кабинет КГД (токен ЛС). Пока не подключено — показать не можем."})

    # --- профиль из КГД (карточка, если синхронизирована) ---
    req = tp["requisites"]
    if isinstance(req, str):
        import json as _json
        req = _json.loads(req) if req else {}
    card = (req or {}).get("kgd_card") or {}
    profile = {
        "iin_bin": tp["iin_bin"], "kind": tp["kind"], "regime": tp["tax_regime"],
        "ugd_code": tp["ugd_code"], "ugd_name": card.get("ugd_name"),
        "oked": tp["oked"],
        "birth_date": tp["birth_date"].isoformat() if tp["birth_date"] else None,
        "begin_date": card.get("begin_date"),
        "active": card.get("active"),
        "is_nds_payer": card.get("is_nds_payer"),
        "kgd_name": card.get("name"),
        "snr_type": card.get("snr_type"),
        "snr_type_name": card.get("snr_type_name"),
        "snr_begin_date": card.get("snr_begin_date"),
        "synced_at": card.get("synced_at"),
        "warnings": card.get("warnings") or [],
    }
    # расхождение режима: что заведено у нас vs что говорит КГД
    _SNR_TO_REGIME = {"SNR_SIMPLIFIED_DECLARATION": "snr_simplified", "SNR_GENERAL_ORDER": "our"}
    kgd_regime = _SNR_TO_REGIME.get(card.get("snr_type"))
    if kgd_regime and kgd_regime != tp["tax_regime"]:
        issues.append({
            "tone": "danger", "title": "Режим по КГД отличается от заведённого",
            "text": f"В системе — {tp['tax_regime']}, а по КГД: «{card.get('snr_type_name')}» "
                    f"с {card.get('snr_begin_date')}. Налоги считаются не по тому режиму — исправьте профиль."})
    if not card.get("synced_at"):
        issues.append({"tone": "warn", "title": "Профиль не сверен с КГД",
                       "text": "Нажмите «↻ КГД», чтобы подтянуть режим, статус и НДС из реестра."})

    return {
        "taxpayer": {"id": str(tp["id"]), "name": tp["name"], "kind": tp["kind"],
                     "regime": tp["tax_regime"], "iin_bin": tp["iin_bin"]},
        "profile": profile,
        "as_of": today.isoformat(),
        "total_due": str(total_due),
        "taxes": [{**t, "amount": str(t["amount"])} for t in taxes],
        "debt": {"total": str(debt_total), "penalty": str(penalty),
                 "has_arrest": bool(debt and debt["has_bank_arrest"]),
                 "status": "ok" if debt is not None else "not_connected",
                 "note": None if debt is not None else "Требует токен ЛС (вход по ЭЦП в кабинет КГД)"},
        "snr": snr,
        "issues": issues,
        "counts": {"review_queue": review_queue, "employees": n_employees, "ops_ytd": ops_this_year},
    }
