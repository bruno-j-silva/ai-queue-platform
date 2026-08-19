import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from api.routes.admin_webhooks import router as admin_webhooks_router
from api.routes.jobs import router as jobs_router
from api.routes.webhook_endpoints import router as webhook_endpoints_router
from shared.logging_config import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging("api")
    logger.info("API iniciando")
    yield
    logger.info("API encerrando")


app = FastAPI(
    title="AI Queue Platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(jobs_router)
app.include_router(webhook_endpoints_router)
app.include_router(admin_webhooks_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> PlainTextResponse:
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
