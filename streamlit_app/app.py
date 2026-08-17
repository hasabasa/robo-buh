"""robo-buh — фронт прототипа (Streamlit).

Страницы = основные поверхности продукта. Пока данные-заглушки: каркас
демонстрирует дизайн-систему и сценарии; подключение к backend — по мере
готовности API (Фаза 1+).
"""

import streamlit as st

from ui import badge, load_css, metric_card, money, snr_traffic_light

st.set_page_config(
    page_title="robo-buh — робот-бухгалтер",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded",
)
load_css()

# --- Демо-данные (заменяются на API backend в Фазе 1) ---
DEMO = {
    "taxpayer": "ИП Пример (упрощёнка)",
    "income_h2": 8_450_000,
    "income_ytd": 15_320_000,
    "ipn_rate": 0.04,
    "social_monthly": 21_675,
    "snr_limit": 2_595_000_000,
    "debt": 184_500,
    "penalty_per_day": 78,
    "review_queue": 14,
}

with st.sidebar:
    st.markdown("## 🧾 robo-buh")
    st.caption("Робот-бухгалтер · упрощёнка РК")
    page = st.radio(
        "Разделы",
        ["Дашборд", "Доходы", "Налоги и календарь", "Декларации", "Долги и пени"],
        label_visibility="collapsed",
    )
    st.divider()
    st.selectbox("Налогоплательщик", [DEMO["taxpayer"]])

if page == "Дашборд":
    st.title("Дашборд")
    st.caption("Положение дел по налогам — одним экраном")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("Оборот за полугодие", money(DEMO["income_h2"]),
                    "H2-2026 · нарастающим итогом", "brand")
    with c2:
        ipn = DEMO["income_h2"] * DEMO["ipn_rate"]
        metric_card("ИПН к уплате (прогноз)", money(ipn),
                    f"ставка {DEMO['ipn_rate']:.0%} · уплата до 25.02.2027", "ok")
    with c3:
        metric_card("Соцплатежи в месяц", money(DEMO["social_monthly"]),
                    "ОПВ + ОПВР + СО + ВОСМС · до 25 числа", "brand")
    with c4:
        metric_card("Задолженность", money(DEMO["debt"]),
                    f"пеня растёт на {money(DEMO['penalty_per_day'])}/день", "danger")

    st.write("")
    snr_traffic_light(DEMO["income_ytd"], DEMO["snr_limit"])

    st.write("")
    left, right = st.columns([3, 2])
    with left:
        st.subheader("Ближайшие обязательства")
        st.markdown(
            f"""
            | Срок | Обязательство | Сумма | Статус |
            |---|---|---|---|
            | 25.08.2026 | Соцплатежи за июль | {money(DEMO['social_monthly'])} | {badge('скоро срок', 'warn')} |
            | 15.11.2026 | Форма 200.00 за Q3 | — | {badge('в работе', 'brand')} |
            | 15.02.2027 | Форма 910.00 за H2 | {money(DEMO['income_h2'] * DEMO['ipn_rate'])} | {badge('прогноз', 'brand')} |
            """,
            unsafe_allow_html=True,
        )
    with right:
        st.subheader("Требует внимания")
        st.markdown(
            f"""
            - {badge(str(DEMO['review_queue']) + ' операций', 'warn')} ждут подтверждения
              «доход / не доход»
            - {badge('Долг ' + money(DEMO['debt']), 'danger')} — есть риск ареста счёта
            """,
            unsafe_allow_html=True,
        )

elif page == "Доходы":
    st.title("Доходы")
    st.caption("Все источники → одна книга операций")

    tab_up, tab_review, tab_ledger = st.tabs(
        ["Загрузка", f"Сверка ({DEMO['review_queue']})", "Книга операций"]
    )
    with tab_up:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Банковская выписка")
            st.file_uploader(
                "MT940 · 1CClientBankExchange · CSV/XLSX · PDF",
                type=["sta", "txt", "csv", "xlsx", "pdf"],
                accept_multiple_files=True,
            )
            st.caption("Формат определяется автоматически. PDF распознаёт ИИ "
                       "с проверкой сумм по напечатанным итогам.")
        with c2:
            st.subheader("Автоматические источники")
            st.markdown(
                f"""
                - Kaspi Shop API — {badge('подключено', 'ok')}
                - Webkassa (ОФД, наличные) — {badge('не подключено', 'warn')}
                """,
                unsafe_allow_html=True,
            )
    with tab_review:
        st.info("Очередь ручной сверки: операции, где классификатор не уверен, "
                "доход это или нет. Подключается к API в Фазе 1.")
    with tab_ledger:
        st.info("Единая книга операций с фильтрами по источнику и периоду. "
                "Подключается к API в Фазе 1.")

elif page == "Налоги и календарь":
    st.title("Налоги и календарь")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Расчёт за период")
        ipn = DEMO["income_h2"] * DEMO["ipn_rate"]
        st.markdown(
            f"""
            | Строка | Значение |
            |---|---|
            | Оборот H2-2026 | {money(DEMO['income_h2'])} |
            | Ставка ИПН | {DEMO['ipn_rate']:.0%} |
            | **ИПН к уплате** | **{money(ipn)}** |
            | Соцплатежи (мес.) | {money(DEMO['social_monthly'])} |
            """
        )
    with c2:
        st.subheader("Календарь")
        st.info("Полугодовой цикл 910 + квартальный 200 + ежемесячные соцплатежи. "
                "Генерируется из obligations (Фаза 2).")

elif page == "Декларации":
    st.title("Декларации")
    st.markdown(
        f"""
        | Форма | Период | Статус |
        |---|---|---|
        | 910.00 | H1-2026 | {badge('сдана', 'ok')} |
        | 200.00 | Q3-2026 | {badge('черновик', 'brand')} |
        | 910.00 | H2-2026 | {badge('копится оборот', 'brand')} |
        """,
        unsafe_allow_html=True,
    )
    st.write("")
    st.subheader("Подписание")
    st.info(
        "Декларация подписывается ВАШЕЙ ЭЦП на вашем компьютере через NCALayer — "
        "ключ никуда не передаётся. Кнопка появится здесь после генерации XML (Фаза 3)."
    )

elif page == "Долги и пени":
    st.title("Долги и пени")
    c1, c2, c3 = st.columns(3)
    with c1:
        metric_card("Задолженность", money(DEMO["debt"]), "по данным КГД", "danger")
    with c2:
        metric_card("Пеня в день", money(DEMO["penalty_per_day"]),
                    "1,25 × базовая ставка НБРК / 365", "warn")
    with c3:
        metric_card("Арест счёта", "риск", "при неуплате по уведомлению", "danger")
    st.write("")
    st.info("Живые данные — из открытого сервиса КГД по ИИН/БИН (Фаза 2).")
