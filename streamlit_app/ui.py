"""UI-хелперы дизайн-системы robo-buh + тонкий клиент backend API."""

import os
from datetime import date
from pathlib import Path

import httpx
import streamlit as st

_ASSETS = Path(__file__).parent / "assets"
API_BASE = os.environ.get("BACKEND_URL", "http://backend:8000")


def load_css() -> None:
    st.markdown(f"<style>{(_ASSETS / 'styles.css').read_text()}</style>", unsafe_allow_html=True)


# ─────────────────────────── backend API ───────────────────────────

def api_get(path: str, **params):
    """GET к backend. Возвращает (data, error). Прямой запрос, без кэша."""
    try:
        r = httpx.get(f"{API_BASE}{path}", params=params, timeout=20.0)
        if r.status_code == 200:
            return r.json(), None
        return None, f"{r.status_code}: {r.text[:160]}"
    except Exception as e:  # noqa: BLE001
        return None, str(e)


# ─────────────────────────── форматирование ───────────────────────────

def money(x) -> str:
    """1234567.5 → '1 234 568 ₸' (тенге, неразрывные пробелы)."""
    return f"{round(float(x or 0)):,}".replace(",", " ") + " ₸"


def _money_split(x) -> tuple[str, str]:
    whole = f"{round(float(x or 0)):,}".replace(",", " ")
    return whole, "₸"


def _ru_date(iso: str) -> str:
    try:
        return date.fromisoformat(iso).strftime("%d.%m.%Y")
    except Exception:  # noqa: BLE001
        return iso


# ─────────────────────────── компоненты ───────────────────────────

def badge(text: str, tone: str = "brand") -> str:
    return f'<span class="rb-badge {tone}">{text}</span>'


_REGIME = {"snr_simplified": "упрощёнка (СНР)", "our": "ОУР (общий режим)"}
_KIND = {"ip": "ИП", "too": "ТОО"}


def hero(taxpayer: dict, total_due, as_of: str, pills: list[str]) -> None:
    """Герой-блок: сколько должен по всем налогам в этом цикле."""
    whole, cur = _money_split(total_due)
    reg = _REGIME.get(taxpayer.get("regime"), taxpayer.get("regime", ""))
    kind = _KIND.get(taxpayer.get("kind"), "")
    pill_html = "".join(f'<span class="hpill">{p}</span>' for p in pills)
    st.markdown(
        f"""
        <div class="rb-hero">
          <div class="who">🧾 {taxpayer.get('name','')} · {kind} · {reg}</div>
          <div class="cap">К уплате по всем налогам в этом цикле</div>
          <div class="amount">{whole}<small>{cur}</small></div>
          <div class="foot">на {_ru_date(as_of)} · расчёт из книги операций в реальном времени</div>
          <div class="pill-row">{pill_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def tax_row(t: dict) -> None:
    """Строка одного налога: код, название, период, сумма, срок."""
    tone = t.get("tone", "brand")
    st.markdown(
        f"""
        <div class="rb-tax {tone}">
          <div class="code">{t['code'].replace('.00','')}</div>
          <div class="mid">
            <div class="t">{t['label']} · {t['period']}</div>
            <div class="s">{t.get('hint','')}</div>
          </div>
          <div class="right">
            <div class="v">{money(t['amount'])}</div>
            <div class="due">{badge(t['kind'], tone)} · до {_ru_date(t['due'])}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def issue_card(it: dict) -> None:
    tone = it.get("tone", "warn")
    ico = {"warn": "⚠️", "danger": "⛔"}.get(tone, "•")
    st.markdown(
        f"""
        <div class="rb-issue {tone}">
          <div class="ico">{ico}</div>
          <div>
            <div class="tt">{it['title']}</div>
            <div class="tx">{it['text']}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def all_clear(text: str = "Всё сходится — данные разобраны, лимиты в норме") -> None:
    st.markdown(f'<div class="rb-allclear">✅ {text}</div>', unsafe_allow_html=True)


def metric_card(label: str, value: str, sub: str = "", tone: str = "brand") -> None:
    st.markdown(
        f"""
        <div class="rb-card {tone}">
          <div class="rb-label">{label}</div>
          <div class="rb-value">{value}</div>
          {f'<div class="rb-sub">{sub}</div>' if sub else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )


def snr_traffic_light(snr: dict) -> None:
    """Светофор лимита СНР из блока snr бэкенда (zone: green|amber|red)."""
    zone = (snr or {}).get("zone", "green")
    tone = {"green": "ok", "amber": "warn", "red": "danger"}.get(zone, "ok")
    ytd = float(snr.get("ytd_turnover", 0)); limit = float(snr.get("limit", 1) or 1)
    share = ytd / limit if limit else 0.0
    pct = min(share, 1.0) * 100
    st.markdown(
        f"""
        <div class="rb-traffic {tone}">
          <span class="dot"></span>
          <div style="flex:1">
            <div style="font-weight:700">{snr.get('message','Лимит СНР')}</div>
            <div class="rb-sub" style="color:var(--rb-ink-soft);font-size:.83rem">
              {money(ytd)} из {money(limit)} · {share:.2%} лимита упрощёнки (600k МРП/год)
            </div>
            <div class="rb-progress {tone}"><span style="width:{pct:.2f}%"></span></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
