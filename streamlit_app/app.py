"""robo-buh — фронт (Streamlit). Дашборд «сколько должен по всем налогам» на живом backend.

Данные тянутся прямыми запросами к API в реальном времени (без заглушек, без кэша).
Если backend недоступен или налогоплательщиков нет — экран честно об этом говорит.
"""

import streamlit as st

from ui import (all_clear, api_get, api_post, api_upload, badge, hero, issue_card,
                load_css, metric_card, money, ncalayer_sign, snr_traffic_light, tax_row)

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
    if not selected:
        st.info("Выберите налогоплательщика в сайдбаре.")
    else:
        tid = selected["id"]
        tabs = st.tabs(["Загрузка", f"Сверка ({rq})", "Книга операций"])
        with tabs[0]:
            up = st.file_uploader(
                "Выписка (MT940 · 1CClientBankExchange · PDF Kaspi) или ЭСФ (XML)",
                type=["sta", "txt", "csv", "pdf", "xml"], accept_multiple_files=True)
            if up and st.button("Загрузить", type="primary"):
                for f in up:
                    is_esf = f.name.lower().endswith(".xml")
                    path = "/api/income/esf/upload" if is_esf else "/api/income/upload"
                    res, err = api_upload(path, f.name, f.getvalue(), tid)
                    if err:
                        st.error(f"{f.name}: {err}")
                    else:
                        st.success(f"{f.name}: загружено {res.get('imported', 0)} · "
                                   f"доход {res.get('income', 0)} · расход {res.get('non_income', 0)} · "
                                   f"на сверку {res.get('review', 0)}")
            st.caption("Формат определяется автоматически. Разбор локальный — данные наружу не уходят.")
        with tabs[1]:
            queue, _ = api_get("/api/income/review-queue", taxpayer_id=tid)
            if not queue:
                all_clear("Очередь сверки пуста — все операции классифицированы")
            else:
                st.caption("Классификатор не уверен — подтвердите вручную:")
                for op in queue:
                    c1, c2, c3 = st.columns([5, 1, 1])
                    with c1:
                        st.markdown(f"**{money(op['amount'])}** · {op.get('op_date','')} · "
                                    f"КНП {op.get('knp') or '—'} · {(op.get('purpose_text') or '')[:60]}")
                    if c2.button("Доход", key=f"inc{op['id']}"):
                        api_post(f"/api/income/review/{op['id']}", json={"is_income": True})
                        st.rerun()
                    if c3.button("Не доход", key=f"exp{op['id']}"):
                        api_post(f"/api/income/review/{op['id']}", json={"is_income": False})
                        st.rerun()
        with tabs[2]:
            led, _ = api_get("/api/income/ledger", taxpayer_id=tid, limit=200)
            if led:
                import pandas as pd
                df = pd.DataFrame(led)
                df["доход"] = df["is_income"].map({True: "✅", False: "—", None: "❓"})
                df = df[["op_date", "payment_channel", "amount", "knp", "counterparty_name",
                         "purpose_text", "доход", "source"]]
                df.columns = ["Дата", "Напр.", "Сумма", "КНП", "Контрагент", "Назначение", "Доход", "Источник"]
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("Операций пока нет — загрузите выписку.")

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
    st.caption("Расчёт → XML → подпись ВАШЕЙ ЭЦП через NCALayer (ключ остаётся у вас)")
    _XML_EP = {"910.00": "910", "200.00": "200", "300.00": "300", "100.00": "100"}
    _ST_TONE = {"draft": "brand", "signed": "ok", "submitted": "ok", "accepted": "ok"}
    if not selected:
        st.info("Выберите налогоплательщика.")
    else:
        tid = selected["id"]
        decls, err = api_get("/api/declarations", taxpayer_id=tid)
        if err:
            st.error(err)
        elif not decls:
            st.info("Деклараций пока нет. Рассчитайте их на вкладке «Налоги» или в API "
                    "(/api/tax/{форма}/calculate) — они появятся здесь.")
        else:
            for d in decls:
                code, did = d["form_code"], d["id"]
                with st.container(border=True):
                    top = st.columns([3, 1])
                    top[0].markdown(f"### {code} · {d['period_year']} (период {d['period_no']})")
                    top[1].markdown(badge(d["status"], _ST_TONE.get(d["status"], "warn")),
                                    unsafe_allow_html=True)
                    if not d["has_xml"]:
                        if st.button(f"Собрать XML {code}", key=f"xml{did}", type="primary"):
                            res, e2 = api_post(f"/api/tax/{_XML_EP[code]}/{did}/xml")
                            if e2:
                                st.error(f"ФЛК/ошибка: {e2}")
                            else:
                                st.rerun()
                    else:
                        xmld, _ = api_get(f"/api/declarations/{did}/xml")
                        xml_text = (xmld or {}).get("xml", "")
                        with st.expander("Посмотреть XML"):
                            st.code(xml_text[:4000], language="xml")
                        st.download_button("Скачать XML", xml_text, file_name=f"{code}_{d['period_year']}.xml",
                                           key=f"dl{did}")
                        if d["status"] in ("signed", "submitted", "accepted"):
                            st.success(f"Подписано ✓ (статус {d['status']})")
                        else:
                            ncalayer_sign(did, xml_text)

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
