"""Тест markdown-чанкера базы знаний (детерминированный, без сети)."""

from app.rag.indexer import _chunk_markdown


def test_chunks_by_headings():
    md = (
        "# Заголовок файла\n\nвступление\n\n"
        "### ИПН\nиндивидуальный подоходный налог, ставка 4%\n\n"
        "### ВОСМС\nвзносы 5950 тенге в месяц\n"
    )
    chunks = _chunk_markdown(md)
    headings = [h for h, _ in chunks]
    assert "ИПН" in headings and "ВОСМС" in headings
    ipn = next(b for h, b in chunks if h == "ИПН")
    assert "4%" in ipn


def test_ignores_tiny_chunks():
    md = "### x\nа\n"          # тело слишком короткое (<20 симв.)
    assert _chunk_markdown(md) == []


def test_no_headings_returns_whole():
    chunks = _chunk_markdown("просто текст без заголовков достаточной длины для чанка")
    assert len(chunks) == 1 and chunks[0][0] == ""
