"""UI-хелперы дизайн-системы robo-buh + тонкий клиент backend API."""

import os
from datetime import date
from pathlib import Path

import httpx
import streamlit as st

_ASSETS = Path(__file__).parent / "assets"
API_BASE = os.environ.get("BACKEND_URL", "http://backend:8000")          # server-side (Streamlit→backend)
PUBLIC_API = os.environ.get("PUBLIC_BACKEND_URL", "http://localhost:8000")  # browser-reachable (JS→backend)


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


def api_post(path: str, *, json=None, params=None):
    """POST к backend. Возвращает (data, error)."""
    try:
        r = httpx.post(f"{API_BASE}{path}", json=json, params=params, timeout=60.0)
        if r.status_code < 300:
            return (r.json() if r.text else {}), None
        return None, f"{r.status_code}: {r.text[:200]}"
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def api_upload(path: str, filename: str, content: bytes, taxpayer_id: str):
    """Загрузка файла (multipart) на backend."""
    try:
        r = httpx.post(f"{API_BASE}{path}", data={"taxpayer_id": taxpayer_id},
                       files={"file": (filename, content)}, timeout=120.0)
        if r.status_code < 300:
            return r.json(), None
        return None, f"{r.status_code}: {r.text[:200]}"
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


def profile_strip(p: dict) -> None:
    """Карточка налогоплательщика из КГД: ИИН, регистрация, статус, НДС, режим."""
    def field(k, v, tone=""):
        return f'<div class="rb-field"><div class="k">{k}</div><div class="v {tone}">{v}</div></div>'
    reg = _REGIME.get(p.get("regime"), p.get("regime", ""))
    fields = [field("ИИН/БИН", p.get("iin_bin", "—"))]
    if p.get("begin_date"):
        fields.append(field("Зарегистрирован", _ru_date(p["begin_date"])))
    if p.get("active") is not None:
        fields.append(field("Статус", "действующий" if p["active"] else "снят с учёта",
                            "ok" if p["active"] else "danger"))
    if p.get("is_nds_payer") is not None:
        fields.append(field("НДС", "плательщик" if p["is_nds_payer"] else "не плательщик",
                            "warn" if p["is_nds_payer"] else "ok"))
    fields.append(field("Режим", reg))
    if p.get("ugd_code"):
        fields.append(field("УГД", p["ugd_code"]))
    src = "из КГД" if p.get("synced_at") else "не синхронизирован с КГД"
    fields.append(field("Источник", src, "ok" if p.get("synced_at") else "warn"))
    st.markdown(f'<div class="rb-profile">{"".join(fields)}</div>', unsafe_allow_html=True)


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


def ncalayer_sign(declaration_id: str, xml: str, height: int = 220) -> None:
    """Браузерный компонент подписи декларации ЭЦП через NCALayer.

    Подпись выполняется В БРАУЗЕРЕ клиента (NCALayer на 127.0.0.1:13579) — ключ и пароль
    остаются у клиента. Подписанный XML JS шлёт на backend /api/declarations/{id}/sign,
    где сервер верифицирует его через NCANode и фиксирует.
    """
    import json as _json
    import streamlit.components.v1 as components

    payload = _json.dumps(xml)  # безопасно вставляем XML как JS-строку
    html = """
<div style="font-family:-apple-system,'Segoe UI',Roboto,sans-serif">
  <button id="signBtn" style="background:linear-gradient(135deg,#2946C4,#4F46E5);color:#fff;
    border:none;border-radius:11px;padding:.7rem 1.3rem;font-weight:700;font-size:.95rem;cursor:pointer">
    🔏 Подписать ЭЦП через NCALayer</button>
  <div id="st" style="margin-top:.8rem;font-size:.9rem;color:#5A6478;line-height:1.5"></div>
</div>
<script>
const XML = __XML__;
const DECL = "__DECL__";
const API = "__API__";
const st = document.getElementById("st");
const say = (m,c) => { st.innerHTML = m; st.style.color = c||"#5A6478"; };
document.getElementById("signBtn").onclick = () => {
  say("Открываю NCALayer… подтвердите ключ и пароль в окне NCALayer.");
  let ws;
  try { ws = new WebSocket("wss://127.0.0.1:13579"); }
  catch(e){ say("NCALayer не запущен (порт 13579). Запустите NCALayer и повторите.","#E02424"); return; }
  ws.onerror = () => say("Не удалось соединиться с NCALayer. Запущен ли он?","#E02424");
  ws.onopen = () => ws.send(JSON.stringify({
    module:"kz.gov.pki.knca.commonUtils", method:"signXml",
    args:["PKCS12","SIGNATURE",XML,"",""]
  }));
  ws.onmessage = (ev) => {
    let r; try { r = JSON.parse(ev.data); } catch(e){ return; }
    if (r.code === undefined) return;
    ws.close();
    if (String(r.code) !== "200"){ say("NCALayer: "+(r.message||r.code),"#E02424"); return; }
    say("Подписано. Отправляю на проверку…");
    fetch(API+"/api/declarations/"+DECL+"/sign", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({signed_xml: r.responseObject})
    }).then(x => x.json().then(j => ({ok:x.ok, j})))
      .then(({ok,j}) => ok
        ? say("✅ Подпись принята и проверена. Статус декларации: "+(j.status||"signed"),"#0E9F6E")
        : say("Отклонено при проверке: "+(j.detail||JSON.stringify(j)),"#E02424"))
      .catch(e => say("Ошибка отправки на backend: "+e,"#E02424"));
  };
};
</script>
""".replace("__XML__", payload).replace("__DECL__", declaration_id).replace("__API__", PUBLIC_API)
    components.html(html, height=height)


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
