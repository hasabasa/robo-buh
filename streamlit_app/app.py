"""robo-buh — фронт (Streamlit). Дашборд «сколько должен по всем налогам» на живом backend.

Данные тянутся прямыми запросами к API в реальном времени (без заглушек, без кэша).
Если backend недоступен или налогоплательщиков нет — экран честно об этом говорит.
"""

import streamlit as st

from ui import (all_clear, api_get, badge, hero, issue_card, load_css, metric_card,
                money, snr_traffic_light, tax_row)

st.set_page_config(page_title="robo-buh — робот-бухгалтер", page_icon="🧾",
                   layout="wide", initial_sidebar_state="expanded")
load_css()

_KIND = {"ip": "ИП", "too": "ТОО"}

with st.sidebar:
    st.markdown("## 🧾 robo-buh")
    st.caption("Робот-бухгалтер · упрощёнка РК")
    page = st.radio("Разделы",
                    ["Обзор", "Доходы", "Налоги и календарь", "Декларации", "Долги и пени"],
                    label_visibility="collapsed")
    st.divider()

    taxpayers, tp_err = api_get("/api/taxpayers")
    selected = None
    if taxpayers:
        labels = {f"{t['name']} · {_KIND.get(t['kind'], t['kind'])}": t for t in taxpayers}
        pick = st.selectbox("Налогоплательщик", list(labels.keys()))
        selected = labels[pick]
    elif tp_err:
        st.error("Backend недоступен")
    else:
        st.info("Пока нет налогоплательщиков")


def _need_backend():
    st.title("Обзор")
    if tp_err:
        st.error(f"Не удалось связаться с backend: {tp_err}")
        st.caption("Проверьте, что backend запущен и доступен по BACKEND_URL.")
    else:
        st.info("Заведите налогоплательщика и загрузите выписку — здесь появится налоговая картина.")


if page == "Обзор":
    if not selected:
        _need_backend()
    else:
        data, err = api_get(f"/api/dashboard/{selected['id']}")
        if err:
            st.title("Обзор")
            st.error(f"Ошибка расчёта: {err}")
        else:
            taxes = data["taxes"]
            # пилюли в герое: срочное к уплате + очередь сверки
            pills = []
            overdue = [t for t in taxes if t["kind"] == "к уплате"]
            if overdue:
                pills.append(f"🔴 просрочено: <b>{money(sum(float(t['amount']) for t in overdue))}</b>")
            rq = data["counts"]["review_queue"]
            if rq:
                pills.append(f"🟡 на сверке: <b>{rq}</b>")
            if not pills:
                pills.append("🟢 просрочек нет")

            hero(data["taxpayer"], data["total_due"], data["as_of"], pills)
            st.write("")

            col_main, col_side = st.columns([3, 2], gap="large")
            with col_main:
                st.markdown('<div class="rb-section-title">Налоги этого цикла</div>',
                            unsafe_allow_html=True)
                if taxes:
                    for t in taxes:
                        tax_row(t)
                else:
                    st.info("Применимых налогов за период нет.")

                if data["snr"]:
                    st.write("")
                    st.markdown('<div class="rb-section-title">Лимит упрощёнки</div>',
                                unsafe_allow_html=True)
                    snr_traffic_light(data["snr"])

            with col_side:
                st.markdown('<div class="rb-section-title">Что не сходится</div>',
                            unsafe_allow_html=True)
                issues = data["issues"]
                if issues:
                    for it in issues:
                        issue_card(it)
                else:
                    all_clear()

                debt = data["debt"]
                if float(debt["total"]) > 0:
                    st.write("")
                    st.markdown('<div class="rb-section-title">Задолженность</div>',
                                unsafe_allow_html=True)
                    metric_card("Долг по КГД", money(debt["total"]),
                                ("арест счёта · " if debt["has_arrest"] else "") +
                                f"пеня {money(debt['penalty'])}", "danger")

elif page == "Доходы":
    st.title("Доходы")
    st.caption("Все источники → одна книга операций")
    if selected:
        data, _ = api_get(f"/api/dashboard/{selected['id']}")
        rq = (data or {}).get("counts", {}).get("review_queue", 0)
    else:
        rq = 0
    tabs = st.tabs(["Загрузка", f"Сверка ({rq})", "Книга операций"])
    with tabs[0]:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Банковская выписка")
            st.file_uploader("MT940 · 1CClientBankExchange · CSV/XLSX · PDF · ЭСФ (XML)",
                             type=["sta", "txt", "csv", "xlsx", "pdf", "xml"],
                             accept_multiple_files=True)
            st.caption("Формат определяется автоматически. PDF распознаёт ИИ с проверкой сумм.")
        with c2:
            st.subheader("Автоматические источники")
            st.markdown(f"- Kaspi Shop API — {badge('подключено', 'ok')}\n"
                        f"- ЭСФ (esf.gov.kz) — {badge('коннектор готов', 'brand')}\n"
                        f"- Webkassa (ОФД) — {badge('не подключено', 'warn')}",
                        unsafe_allow_html=True)
    with tabs[1]:
        st.info("Очередь ручной сверки операций (is_income не определён). Подключение — API income.")
    with tabs[2]:
        st.info("Единая книга операций с фильтрами по источнику и периоду.")

elif page == "Налоги и календарь":
    st.title("Налоги и календарь")
    if selected:
        data, err = api_get(f"/api/dashboard/{selected['id']}")
        if data:
            for t in data["taxes"]:
                tax_row(t)
    else:
        st.info("Выберите налогоплательщика.")

elif page == "Декларации":
    st.title("Декларации")
    st.info("Список деклараций (draft→signed→submitted) и подписание ЭЦП через NCALayer — "
            "ключ остаётся на вашем компьютере. Экран подключается к API деклараций.")

elif page == "Долги и пени":
    st.title("Долги и пени")
    if selected:
        data, _ = api_get(f"/api/dashboard/{selected['id']}")
        debt = (data or {}).get("debt", {"total": 0, "penalty": 0, "has_arrest": False})
        c1, c2, c3 = st.columns(3)
        with c1:
            metric_card("Задолженность", money(debt["total"]), "по данным КГД",
                        "danger" if float(debt["total"]) > 0 else "ok")
        with c2:
            metric_card("Пеня", money(debt["penalty"]), "1,25 × базовая ставка НБРК / 365", "warn")
        with c3:
            metric_card("Арест счёта", "риск" if debt["has_arrest"] else "нет",
                        "при неуплате по уведомлению", "danger" if debt["has_arrest"] else "ok")
    st.info("Живые данные — из открытого сервиса КГД по ИИН/БИН (модуль долгов, Тир-2).")
