# robo-buh — рабочие заметки (контекст проекта)

Робот-бухгалтер для МСБ Казахстана на **упрощёнке (СНР на основе упрощённой декларации)**.
Отдельный продукт (не модуль SellerIQ). Репо: `github.com/hasabasa/robo-buh`.

## Что это (MVP, продукт A)

Собирает доход из выписок → классифицирует → считает налог **910.00** (ИПН 4% / КПН для ТОО,
маслихат 2–6%) + соцплатежи ИП + пеню → генерирует XML → клиент подписывает **своей ЭЦП**
(NCALayer, ключ не покидает клиента) → сдача в КГД. Плюс RAG «спроси бухгалтера».

**Вне MVP:** ЭСФ, ОУР (форма 100.00/300.00), 1С-интеграция, зарплата (200.00) сверх соцплатежей.
Трек B (надстройка над 1С для ОУР / сверка тендеров) — сильный спрос, но отдельный продукт, потом.

## Стек и запуск

`backend/` FastAPI+asyncpg (Python 3.12) · `streamlit_app/` фронт прототипа · `docker/` compose
(backend, streamlit, postgres, redis, **ncanode**). Таблицы — `init_db()` при старте (без alembic).

```bash
cp .env.example .env          # заполнить ключи (см. ниже)
docker-compose -f docker/docker-compose.yml up -d --build   # только docker-compose (v1), не 'docker compose'
# backend :8000/docs · streamlit :8501 · health: curl localhost:8000/health
# тесты: docker cp backend/tests robobuh_backend:/app/tests && docker exec robobuh_backend python -m pytest tests/ -q
```
⚠️ `restart` НЕ перечитывает env_file — после правки `.env` делать `up -d` (пересоздание).
⚠️ `docker cp backend/tests robobuh_backend:/app/tests` при существующей папке вкладывает внутрь —
перед копированием `docker exec robobuh_backend rm -rf /app/tests`.

## Архитектура (сквозной поток)

```
выписка (MT940 / 1CClientBankExchange / PDF-OCR)
  → парс + автоклассификатор по КНП (доход/не-доход/на-сверку; расход всегда не доход)
  → income_ledger (идемпотентный UPSERT, уверенное→confirmed, неопознанное→pending/очередь сверки)
  → расчёт 910.00 (оборот×ставка + соцплатежи + светофор лимита СНР 600k МРП)
  → XML (провизорный, см. каветы) + локальный ФЛК
  → подпись ЭЦП клиента (NCALayer→XMLDSIG) → верификация NCANode
  → сдача (Smart Bridge SOAP, оргтрек) / handoff в Кабинет ИСНА
```

### Модули backend (`backend/app/`)
- `ingestion/` — `mt940_parser`, `client_bank_1c`, `pdf_ocr` (qwen3-6 vision), `kz_entities`
  (ИИН/БИН/ИИК/КНП/КБе regex), `knp_classifier`, `alem_client` (Alem LLM/vision/embed), `service`
  (detect_and_parse автодетект формата + upsert).
- `tax/` — `simplified_910` (ИПН/КПН + светофор СНР), `social` (ОПВ/ОПВР/СО/ВОСМС ИП),
  `penalty` + `nbrk_rates` (пеня по под-периодам), `xml_910` + `flk` + `xml_service`, `service`.
- `signing/` — `ncanode` (verify XML + sign для тестов), `service` (приём подписанного XML → аудит
  document_signatures + сверка БИН подписанта).
- `rag/` — `indexer` (docs/knowledge → чанки → эмбеддинги text-1024), `service` (косинус top-k → qwen3-6).
- `routers/` — health, taxpayers, income (`/upload`, `/review-queue`), tax (`/910/calculate`,
  `/910/{id}/xml`, `/penalty`), signing (`/declarations/{id}/xml|sign`), kb (`/reindex`, `/ask`).

Тестов: ~33 (юнит движков/парсеров/классификатора + харнесс подписи). Всё коммитится, e2e проверено.

## Env / ключи (в `.env`, gitignore — НЕ коммитить)

- **Alem Plus** (грант Астана Хаб, OpenAI-совместимый `llm.alem.ai/v1`, у каждой модели свой ключ):
  `ALEM_VISION_KEY` (qwen3-6 — OCR-разбор + классификация), `ALEM_OCR_KEY` (deepseek-ocr),
  `ALEM_EMBED_KEY` (text-1024, 1024-мерн). ⚠️ Ключи светились в чате 18.08 → **перевыпустить**.
  Vision только через `data:image;base64` (внешние URL 403). qwen3-6 thinking mode → max_tokens≥3000.
- `NCANODE_URL=http://ncanode:14579` — сервер только ВЕРИФИЦИРУЕТ подпись, ключи клиентов не хранит.
- Postgres — через `env_file` в compose.

## Тест-субъекты

- **ИП ИИН 001201000056** (рождён 01.12.2000 → ОПВР применяется) — реальный клиент для 910.00.
- **ТОО "CS"** (БИН 260440029440) — на **ОУР**, это **ОПЕРАТОР** robo-buh (Smart Bridge, ЭЦП,
  Астана Хаб), НЕ клиент-упрощенец. Не заводить как налогоплательщика-клиента.
- ЭЦП (GOST-p12) в `~/Desktop/hasa/все ЭЦП/`, пароли там же. Подписывать — только сам владелец
  через NCALayer; в код/логи пароли не тащить.

## ⚠️ Критичные каветы (не забыть)

1. **XML 910.00 — ПРОВИЗОРНЫЙ.** Официальный машинный шаблон СОНО (form_910_00_v27_r133, в
   `docs/knowledge/sono/910.00/`) — старый режим **3%+соцналог**, версии под НК-2026 (4%, без
   соцналога) НЕТ. К `field_910_00_NNN` не привязываемся. Достоверны только строки 001–004;
   соцплатежи эмитим семантически (`social.*`), НЕ кодами 910.00.005–010. Вотчер:
   `kgd.gov.kz/ru/content/fno-na-2026-god-1` — как выйдет 2026-шаблон, привязать.
2. **Наша логика 4% / соцналог отменён — верна для НК-2026** (`kz_2026.py`). Не менять на 3%.
3. **Пеня:** при новом решении НБРК дописать строку в `nbrk_rates.RATE_HISTORY` (текущая база
   16,75% с 27.07.2026). Движок сам ставит флаг `stale` за пределами известных ставок.
4. **OCR** доказан на синтетике; финальный тюнинг промпта — на РЕАЛЬНОЙ выписке (ждём образец).
5. **Вычет по ИПН:** глоссарий говорит 30 МРП, офиц. калькулятор КГД — 14 МРП. Для 200.00 (Фаза 2)
   сверять по правилам, не по глоссарию.

## КГД: сдача и справочные сервисы

- **Транспорт приёма ФНО — SOAP+WS-Security поверх IPSec-VPN к ВШЭП** (не REST). Два сервиса,
  ДВЕ заявки в Smart Bridge (`sb.egov.kz`, вход ЭЦП юрлица): **SONO_FNO_SEND (KGD-S-0363)**,
  **SONO_FNO_GET_STATUS (KGD-S-0362)**. Нужен статич. публичный IP + PSK от АО НИТ.
- **Подпись XML — ЭЦП самого налогоплательщика (клиента), НЕ оператора.**
- **REST-справки (без VPN)** `portal.kgd.gov.kz/services/isnaportalsync/public/`, заголовок
  `X-Portal-Token`. Тир-1 (оператор-токен, любой БИН): `find-taxpayer`, `find-nds-payer-service`,
  `unreliable-taxpayers`, `snr` (гейт «только упрощёнка», уточнить публичность). Тир-2 (нужен токен
  клиента): `info-absence-tax-debt`, `taxpayer-accruals`, `paid-amounts`, `excessive-paid`.
- **Токен `X-Portal-Token`** — прямой ссылки НЕТ: на портале под ЭЦП кнопка «Создать обращение» →
  заявка, либо Администратор КГД / 1414. Запрашивать сразу на весь список Тир-1.
- Порталы КГД/SB — React-SPA (react4xp); контент/PDF-инструкции достаются с файлового сервера
  `kgd.gov.kz/sites/default/files/...`. Машинные шаблоны СОНО: `.tar.bz2` с обрезанной сигнатурой
  `BZ` (дописать перед bunzip2).

## Переиспользование (из соседних репо)

- **cube-demper** (`~/Documents/GitHub/cube-demper-full`) — контур ЭЦП (signing_service/NCANode,
  ncalayer.ts, страница подписания), онбординг phone+SMS-навсегда, каркас налог-калькулятора.
- **cube-translator** (`github.com/hasabasa/cube-translator`) — авторский OCR-движок (llm_client
  с failover/thinking, entity_filter, pdf_scan_pipeline) → OCR выписок.
- **SellerIQ** (`~/Documents/GitHub/Seller-IQ`) — Kaspi Shop API (доход маркетплейса), Qwen-клиент,
  биллинг Kaspi Pay (касса для оплаты подписки на сам сервис, НЕ источник дохода клиента).

## Открытые задачи

- P0: XML под НК-2026 (ждём шаблон КГД) · тюнинг OCR на реальной выписке.
- P1: REST-клиент КГД Тир-1 (нужен `X-Portal-Token`) — гейт онбординга + валидация + риск контрагентов.
- Оргтрек (владелец): заявки Smart Bridge от ТОО "CS", `X-Portal-Token` через «Создать обращение»,
  статич. публичный KZ-IP под VPN.
- Позже: модуль долгов (Тир-2, токен клиента), UI подписания на фронте, CSV/XLSX-парсеры банков.

Детали разведки КГД — память `kgd-official-sources`. Арсенал Alem — `alem-ai-arsenal`.
Почему Kaspi Pay не источник — `kaspi-pay-accounting-dead-end`.

## ЭСФ-коннектор (Фаза B) — ПОЛНОСТЬЮ ДОКАЗАН НА ПРОДЕ 26.08.2026

Источник для НДС-движка (300.00) + сверки контуров. SDK разобран (esf-sdk, 189МБ,
kgd.gov.kz/sites/default/files/ftpdata/ESF/): 30 WSDL, 60 XSD, SoapUI-проект, RSA+GOST тест-серты.

**Парсер счёта — ГОТОВ** (`ingestion/esf_parser.py`): invoiceContainer XML → ledger с НДС,
направление по БИН владельца (продавец→реализация/исходящий, покупатель→закупка/входящий),
namespace-agnostic (v1/v2). `POST /api/income/esf/upload`. E2E: ЭСФ → ledger → 300.00.

**SOAP-транспорт (`esf/soap.py`) — весь флоу отработал вживую на esf.gov.kz (прод):**
- База ВСЕХ сервисов (вкл. Version): `esf.gov.kz:8443/esf-web/ws/api1/` (прод),
  `test3.esf.kgd.gov.kz:8443/esf-web/ws/api1/` (тест). `esf-test.kgd.gov.kz:9443` — МЁРТВ.
- **Version:** элемент `esfVersionRequest` (НЕ getEsfVersion…), пустой SOAPAction → `InvoiceV2`.
- **Вход (доказан на проде):** `AuthService/createAuthTicket(iin)` → сервер отдаёт `authTicketXml`
  (свои `timeMark`+`state`) → клиент подписывает enveloped-XMLDSIG внутри `<authSign>` →
  `SessionService/createSessionSigned` → sessionId вида `<hex>-<БИН>--ADMIN_ENTERPRISE`.
  `tin`=БИН → МУЛЬТИТЕНАНТ. Подписанный тикет — сырым XML в `<signedAuthTicket>` (экранирован).
- **❗ createSessionSigned И closeSession требуют `wsse:Security/UsernameToken`** в SOAP-Header
  (`mustUnderstand=1`): `Username`=ИИН, `Password`=пароль **КАБИНЕТА ЭСФ** (esf.gov.kz), НЕ PIN ключа
  и НЕ пароль p12. Без него — `A security error was encountered when verifying the message`.
  С неверным паролем в тикете (протухшим) — `SIGNATURE_INVALID_FORMAT`. Аккаунт-пароль задаётся
  при регистрации в ЭСФ; вход в кабинет по ЭЦП его не отменяет.
- **queryInvoice / queryInvoiceById — БЕЗ заголовка** (сессия уже в sessionId). Порядок элементов
  criteria строгий по XSD: `direction, dateFrom, dateTo, asc, pageNum` (иначе `cvc-complex-type`).
  direction: `OUTBOUND` (выданные=реализация) / `INBOUND` (полученные=закупки). **Лимит: ≤1 квартала
  на запрос** («Можно получить список СФ за период не более 1 квартала») → бить период поквартально.
  Ответ: `rsCount` + `invoiceInfoList`; полные счета — `queryInvoiceById(idList)` → парсер.
- **Одна сессия на пользователя:** повторный createSessionSigned → `User already has opened session`.
  Закрывать `closeSession` (status CLOSED). ESF-сессия живёт ~20+ мин.
- **Подпись:** прод — клиент через **NCALayer** (`wss://127.0.0.1:13579`, commonUtils.signXml,
  ключ AUTHENTICATION, GOST-512, enveloped, c14n `#WithComments`) — ключ и его пароль у клиента,
  бэкенд не держит. `open_session(tin, iin, account_password, sign_fn)` — sign_fn инъектируется.
  Тесты — RSA тест-серт SDK через `signxml` (пин **`Qwerty12`**; p12 legacy, `cryptography`==50 грузит).
- **⚠️ ТОО CS (оператор) — НЕ плательщик НДС, ЭСФ у него 0** во всех кварталах 2024–2026 (проверено
  вживую, обе стороны). Для валидации 300.00 на реальных данных нужен НДС-клиент. Обороты ТОО CS
  шли банком, не через ЭСФ. Оператор-реквизиты: ИИН 040331550432, БИН 260440029440.
- **Не доделано (нужен НДС-клиент с реальными ЭСФ):** live-разбор `queryInvoiceById`→invoiceContainer
  через парсер (код готов, не на чем проверить). Host-раннер: `scratchpad/esf_prod_read.py` (+venv
  `esfvenv` с websocket-client). Пароль кабинета в git/scratchpad НЕ хранится — затёрт после прогона.
