from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from technical_document_ml_service.api.errors import register_exception_handlers
from technical_document_ml_service.api.routers import (
    auth_router,
    balance_router,
    health_router,
    history_router,
    predict_router,
    tasks_router,
    users_router,
)
from technical_document_ml_service.db.init_db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Technical Document ML Service",
    lifespan=lifespan,
)

register_exception_handlers(app)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(balance_router)
app.include_router(history_router)
app.include_router(predict_router)
app.include_router(tasks_router)