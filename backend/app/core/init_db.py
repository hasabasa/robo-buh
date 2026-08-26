"""Схема БД robo-buh. Таблицы создаются идемпотентно при старте (идиома SellerIQ,
alembic не используется). Каждый ALTER — через IF NOT EXISTS-гард.

Ядро модели (см. план продукта):
  taxpayers            — кто налогоплательщик (ИП/ТОО на упрощёнке)
  employees            — работники (для формы 200.00)
  income_ledger        — единая книга операций дохода из всех источников
  declarations         — формы 910.00/200.00 и их жизненный цикл
  document_signatures  — аудит подписей ЭЦП (портировано из cube-demper)
  obligations          — календарь обязательств (сроки, суммы, пеня)
"""

import logging

import asyncpg

logger = logging.getLogger(__name__)

DDL = [
    # --- Пользователи сервиса (владелец бизнеса или бухгалтер, ведущий многих) ---
    """
    CREATE TABLE IF NOT EXISTS users (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        phone TEXT UNIQUE NOT NULL,
        full_name TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        settings JSONB NOT NULL DEFAULT '{}'::jsonb
    );
    """,
    # --- Налогоплательщики: user 1:N taxpayers (бухгалтер ведёт нескольких) ---
    """
    CREATE TABLE IF NOT EXISTS taxpayers (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        kind TEXT NOT NULL CHECK (kind IN ('ip', 'too')),
        iin_bin CHAR(12) NOT NULL,
        name TEXT NOT NULL,
        tax_regime TEXT NOT NULL DEFAULT 'snr_simplified'
            CHECK (tax_regime IN ('snr_simplified', 'our')),
        oked TEXT,
        ugd_code TEXT,                 -- код органа госдоходов
        maslikhat_rate NUMERIC(4,2),   -- ставка ИПН решением маслихата (NULL = базовая 4%)
        birth_date DATE,               -- для ИП: ОПВР 3,5% только для р. после 01.01.1975
        kaspi_api_token TEXT,          -- вечный X-Auth-Token Kaspi Shop API (если продаёт на Kaspi)
        requisites JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (user_id, iin_bin)
    );
    """,
    # --- Работники (форма 200.00; у ТОО минимум директор) ---
    """
    CREATE TABLE IF NOT EXISTS employees (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        taxpayer_id UUID NOT NULL REFERENCES taxpayers(id) ON DELETE CASCADE,
        iin CHAR(12) NOT NULL,
        full_name TEXT NOT NULL,
        salary NUMERIC(14,2) NOT NULL DEFAULT 0,
        is_resident BOOLEAN NOT NULL DEFAULT TRUE,
        hired_at DATE,
        fired_at DATE,
        birth_date DATE,               -- ОПВР работника
        deductions JSONB NOT NULL DEFAULT '{}'::jsonb,  -- вычеты (стандартный и др.)
        UNIQUE (taxpayer_id, iin)
    );
    """,
    # --- Единая книга операций дохода ---
    """
    CREATE TABLE IF NOT EXISTS income_ledger (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        taxpayer_id UUID NOT NULL REFERENCES taxpayers(id) ON DELETE CASCADE,
        source TEXT NOT NULL CHECK (source IN
            ('kaspi_api','bank_mt940','bank_1c','bank_csv','bank_pdf','ofd_webkassa','manual')),
        external_id TEXT NOT NULL,     -- id операции в источнике (для идемпотентности)
        op_date DATE NOT NULL,
        op_datetime TIMESTAMPTZ,
        amount NUMERIC(14,2) NOT NULL, -- положительная = приход
        currency CHAR(3) NOT NULL DEFAULT 'KZT',
        counterparty_name TEXT,
        counterparty_bin_iin CHAR(12),
        counterparty_iik TEXT,
        knp CHAR(3),                   -- код назначения платежа (НБРК)
        kbe CHAR(2),
        purpose_text TEXT,
        payment_channel TEXT,          -- card/qr/cash/transfer/settlement/...
        -- Классификация: NULL = не решено (очередь сверки), TRUE = доход, FALSE = не доход
        is_income BOOLEAN,
        confidence NUMERIC(3,2),       -- уверенность классификатора 0..1
        classified_by TEXT CHECK (classified_by IN ('knp_rule','direction','qwen','human','unknown') OR classified_by IS NULL),
        -- Дедупликация: одна продажа может прийти чеком ОФД и зачислением банка
        dedup_group_id UUID,
        duplicate_of UUID REFERENCES income_ledger(id),
        status TEXT NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending','confirmed','excluded')),
        raw_payload JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (taxpayer_id, source, external_id)
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_ledger_taxpayer_date
        ON income_ledger (taxpayer_id, op_date);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_ledger_review_queue
        ON income_ledger (taxpayer_id) WHERE is_income IS NULL;
    """,
    # --- Декларации (910.00 / 200.00) ---
    """
    CREATE TABLE IF NOT EXISTS declarations (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        taxpayer_id UUID NOT NULL REFERENCES taxpayers(id) ON DELETE CASCADE,
        form_code TEXT NOT NULL CHECK (form_code IN ('910.00','200.00','300.00','100.00')),
        period_year INT NOT NULL,
        period_no INT NOT NULL,        -- 910: 1..2 (полугодие); 200: 1..4 (квартал)
        kind TEXT NOT NULL DEFAULT 'regular'
            CHECK (kind IN ('regular','additional','liquidation')),
        status TEXT NOT NULL DEFAULT 'draft'
            CHECK (status IN ('draft','confirmed','signed','submitted','accepted','rejected')),
        calc JSONB NOT NULL DEFAULT '{}'::jsonb,   -- построчный расчёт формы
        xml TEXT,                                   -- сгенерированный ФНО-XML
        xsd_version TEXT,
        flk_report JSONB,                           -- результат локального ФЛК
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (taxpayer_id, form_code, period_year, period_no, kind)
    );
    """,
    # --- Аудит подписей ЭЦП (схема из cube-demper document_signatures, адаптирована) ---
    """
    CREATE TABLE IF NOT EXISTS document_signatures (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        declaration_id UUID NOT NULL REFERENCES declarations(id) ON DELETE CASCADE,
        signer_iin CHAR(12),
        signer_bin CHAR(12),
        signer_name TEXT,
        signature_kind TEXT NOT NULL DEFAULT 'xmldsig'
            CHECK (signature_kind IN ('xmldsig','cms')),
        signature TEXT NOT NULL,           -- XMLDSIG-блок или CMS base64
        certificate_serial TEXT,
        certificate_not_before TIMESTAMPTZ,
        certificate_not_after TIMESTAMPTZ,
        certificate_issuer TEXT,
        verified BOOLEAN NOT NULL DEFAULT FALSE,
        verification_details JSONB,
        signed_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """,
    # --- Календарь обязательств ---
    """
    CREATE TABLE IF NOT EXISTS obligations (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        taxpayer_id UUID NOT NULL REFERENCES taxpayers(id) ON DELETE CASCADE,
        kind TEXT NOT NULL CHECK (kind IN
            ('ipn_910','social_monthly','form_200','vosms','custom')),
        title TEXT NOT NULL,
        due_date DATE NOT NULL,
        amount NUMERIC(14,2),
        status TEXT NOT NULL DEFAULT 'upcoming'
            CHECK (status IN ('upcoming','due','paid','overdue')),
        penalty_accrued NUMERIC(14,2) NOT NULL DEFAULT 0,
        meta JSONB NOT NULL DEFAULT '{}'::jsonb,
        UNIQUE (taxpayer_id, kind, due_date)
    );
    """,
    # --- RAG-база знаний: чанки глоссария/НК/КНП + эмбеддинги (text-1024, 1024-мерн.) ---
    """
    CREATE TABLE IF NOT EXISTS kb_chunks (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        doc TEXT NOT NULL,
        heading TEXT,
        chunk_text TEXT NOT NULL,
        embedding JSONB NOT NULL,        -- нормализованный вектор (косинус = скаляр)
        content_hash TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (doc, content_hash)
    );
    """,
    # --- [Продукт B] Формы 300.00/100.00 в declarations.form_code ---
    """
    DO $$ BEGIN
        ALTER TABLE declarations DROP CONSTRAINT IF EXISTS declarations_form_code_check;
        ALTER TABLE declarations ADD CONSTRAINT declarations_form_code_check
            CHECK (form_code IN ('910.00','200.00','300.00','100.00'));
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;
    """,
    # --- [Продукт B: ОУР] Допускаем режим 'our' в taxpayers.tax_regime ---
    """
    DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM information_schema.constraint_column_usage
                   WHERE table_name='taxpayers' AND constraint_name='taxpayers_tax_regime_check') THEN
            ALTER TABLE taxpayers DROP CONSTRAINT taxpayers_tax_regime_check;
        END IF;
        ALTER TABLE taxpayers ADD CONSTRAINT taxpayers_tax_regime_check
            CHECK (tax_regime IN ('snr_simplified', 'our'));
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;
    """,
    # --- [Продукт B: ОУР] Расширение ledger на расходную сторону и НДС ---
    # Гарды IF NOT EXISTS — идиома проекта (без alembic). Для упрощёнки (A) поля не
    # используются; для ОУР (B): НДС в составе операции (зачёт входного), категория
    # расхода и вычитаемость по КПН. Направление уже есть в payment_channel (credit/debit).
    """
    DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name='income_ledger' AND column_name='vat_amount') THEN
            ALTER TABLE income_ledger ADD COLUMN vat_amount NUMERIC(14,2);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name='income_ledger' AND column_name='vat_rate') THEN
            ALTER TABLE income_ledger ADD COLUMN vat_rate NUMERIC(4,2);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name='income_ledger' AND column_name='expense_category') THEN
            ALTER TABLE income_ledger ADD COLUMN expense_category TEXT;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name='income_ledger' AND column_name='is_deductible') THEN
            ALTER TABLE income_ledger ADD COLUMN is_deductible BOOLEAN;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name='income_ledger' AND column_name='esf_id') THEN
            ALTER TABLE income_ledger ADD COLUMN esf_id TEXT;  -- регистрационный номер ЭСФ
        END IF;
    END $$;
    """,
    # --- Снимки задолженности из открытого сервиса КГД ---
    """
    CREATE TABLE IF NOT EXISTS debt_snapshots (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        taxpayer_id UUID NOT NULL REFERENCES taxpayers(id) ON DELETE CASCADE,
        total_debt NUMERIC(14,2) NOT NULL DEFAULT 0,
        penalty NUMERIC(14,2) NOT NULL DEFAULT 0,
        has_bank_arrest BOOLEAN,
        details JSONB,
        fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """,
]


async def init_db(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        for stmt in DDL:
            await conn.execute(stmt)
    logger.info("✅ Схема БД robo-buh проверена/создана (%d statements)", len(DDL))
