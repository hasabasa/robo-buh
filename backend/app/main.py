"""robo-buh backend — робот-бухгалтер для упрощёнки РК."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .core.database import close_pool, get_pool
from .core.init_db import init_db
from .routers import health, signing, taxpayers

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

app.include_router(health.router, tags=["service"])
app.include_router(taxpayers.router, prefix="/api/taxpayers", tags=["taxpayers"])
app.include_router(signing.router, prefix="/api/declarations", tags=["signing"])
