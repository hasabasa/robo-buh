"""UI-хелперы дизайн-системы robo-buh для Streamlit."""

from pathlib import Path

import streamlit as st

_ASSETS = Path(__file__).parent / "assets"


def load_css() -> None:
    st.markdown(
        f"<style>{(_ASSETS / 'styles.css').read_text()}</style>",
        unsafe_allow_html=True,
    )


def money(x: float | int) -> str:
    """1234567.5 → '1 234 568 ₸' (тенге, неразрывные пробелы)."""
    return f"{round(float(x)):,}".replace(",", " ") + " ₸"


def metric_card(label: str, value: str, sub: str = "", tone: str = "brand") -> None:
    """Карточка-метрика. tone: brand | ok | warn | danger."""
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


def badge(text: str, tone: str = "brand") -> str:
    return f'<span class="rb-badge {tone}">{text}</span>'


def snr_traffic_light(income_ytd: float, limit_kzt: float) -> None:
    """Светофор лимита СНР: зелёный <80%, янтарный 80–100%, красный ≥100%."""
    share = income_ytd / limit_kzt if limit_kzt else 0.0
    tone = "ok" if share < 0.8 else ("warn" if share < 1.0 else "danger")
    label = {
        "ok": "Запас по лимиту СНР",
        "warn": "Приближаетесь к лимиту СНР",
        "danger": "Лимит СНР превышен — риск слёта с упрощёнки",
    }[tone]
    pct = min(share, 1.0) * 100
    st.markdown(
        f"""
        <div class="rb-traffic {tone}">
          <span class="dot"></span>
          <div style="flex:1">
            <div style="font-weight:600">{label}</div>
            <div class="rb-sub" style="color:var(--rb-ink-soft);font-size:0.82rem">
              {money(income_ytd)} из {money(limit_kzt)} ({share:.1%})
            </div>
            <div class="rb-progress {tone}"><span style="width:{pct:.1f}%"></span></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
