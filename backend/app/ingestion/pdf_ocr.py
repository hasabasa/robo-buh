"""OCR банковских выписок в PDF → структурированные операции.

Путь: PDF-страница → PNG (PyMuPDF/fitz) → base64 → vision-модель Alem (deepseek-ocr,
фолбэк qwen3-6) → JSON-массив операций. Архитектура рендера и base64-подачи взята из
cube-translator (core/pdf_scan_pipeline.py, авторский движок владельца); промпт
переписан с «перевод документа» на «извлечение банковских операций».

Применяется ТОЛЬКО когда у PDF нет текстового слоя (скан). PDF с текстом разбирается
дешевле обычным парсером (pdf_parser), без обращения к vision.
"""

from __future__ import annotations

import json
import logging

from .alem_client import AlemClient

logger = logging.getLogger(__name__)

# DPI рендера: 200 — компромисс качества/размера base64 для мелкого табличного текста выписки.
RENDER_DPI = 200

OCR_SYSTEM = (
    "Ты извлекаешь операции из банковской выписки Казахстана. Верни СТРОГО JSON-массив, "
    "без пояснений, без markdown. Каждый элемент — одна операция:\n"
    '{"date":"ДД.ММ.ГГГГ", "amount":число, "direction":"credit"|"debit", '
    '"counterparty":"наименование или null", "counterparty_bin_iin":"12 цифр или null", '
    '"iik":"KZ... или null", "knp":"3 цифры или null", "purpose":"полный текст назначения"}\n'
    "ПРАВИЛО НАПРАВЛЕНИЯ (важно!): если в строке 'Кредит'/'Приход'/'Поступление'/'+' — "
    "это direction=\"credit\". Если 'Дебет'/'Расход'/'Списание'/'-' — direction=\"debit\". "
    "Смотри именно на колонку кредит/дебет каждой строки, не ставь всем одно значение.\n"
    "amount — всегда положительное число без пробелов и валюты. "
    "purpose — перенеси ВЕСЬ текст назначения платежа строки (вместе с KNP и контрагентом). "
    "Если поля реально нет — null."
)

OCR_USER = (
    "Извлеки ВСЕ операции из этой страницы выписки в JSON-массив. "
    "Не пропускай строки, не выдумывай отсутствующие поля."
)


def render_pdf_to_png(pdf_bytes: bytes, dpi: int = RENDER_DPI) -> list[bytes]:
    """PDF → список PNG по страницам (через PyMuPDF)."""
    import fitz  # PyMuPDF; импорт локальный — тяжёлая нативная зависимость

    pages: list[bytes] = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        for page in doc:
            pix = page.get_pixmap(matrix=matrix)
            pages.append(pix.tobytes("png"))
    finally:
        doc.close()
    return pages


def _parse_ops(raw: str) -> list[dict]:
    """Достаёт JSON-массив из ответа модели (возможны ```json-обёртки и thinking-шум)."""
    s = raw.strip()
    start, end = s.find("["), s.rfind("]")
    if start == -1 or end == -1 or end < start:
        logger.warning("OCR: в ответе не найден JSON-массив (len=%d)", len(s))
        return []
    try:
        data = json.loads(s[start : end + 1])
        return data if isinstance(data, list) else []
    except json.JSONDecodeError as e:
        logger.warning("OCR: не распарсили JSON операций: %s", e)
        return []


async def ocr_statement_pdf(pdf_bytes: bytes, client: AlemClient) -> list[dict]:
    """Скан-выписка PDF → список операций (сырые dict под нормализацию в income_ledger).

    Структурный разбор делает vision-LLM (qwen3-6): читает картинку страницы И сразу
    возвращает JSON-массив операций. deepseek-ocr для этого не годится — он транскрибирует
    в текст, а не в структуру; его держим для сырой транскрипции тяжёлых сканов отдельно.
    """
    pages = render_pdf_to_png(pdf_bytes)
    logger.info("OCR выписки: %d страниц на распознавание", len(pages))
    all_ops: list[dict] = []
    for i, png in enumerate(pages):
        data_url = AlemClient.image_data_url(png, "image/png")
        resp = await client.chat(OCR_SYSTEM, OCR_USER, images=[data_url])
        ops = _parse_ops(resp.content or resp.reasoning or "")
        logger.info("OCR стр. %d/%d: %d операций", i + 1, len(pages), len(ops))
        all_ops.extend(ops)
    return all_ops
