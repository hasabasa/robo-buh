"""robo-buh backend — робот-бухгалтер для упрощёнки РК."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.database import close_pool, get_pool
from .core.init_db import init_db
from .routers import dashboard, health, income, kb, kgd, signing, tax, taxpayers

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await get_pool()
    await init_db(pool)
    yield
    await close_pool()


app = FastAPI(
    title="robo-buh",
    description="Робот-бухгалтер: упрощёнка РК, формы 910.00 и 200.00",
    lifespan=lifespan,
)

# CORS: браузерный компонент подписи (Streamlit-iframe) шлёт подписанный XML на бэкенд.
# Прототип — разрешаем всё; в проде сузить до домена кабинета.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

app.include_router(health.router, tags=["service"])
app.include_router(taxpayers.router, prefix="/api/taxpayers", tags=["taxpayers"])
app.include_router(signing.router, prefix="/api/declarations", tags=["signing"])
app.include_router(tax.router, prefix="/api/tax", tags=["tax"])
app.include_router(income.router, prefix="/api/income", tags=["income"])
app.include_router(kb.router, prefix="/api/kb", tags=["knowledge"])
app.include_router(kgd.router, prefix="/api/kgd", tags=["kgd"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
