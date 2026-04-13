"""FastAPI application entry point.

Registers every router in :mod:`llm_lawyer.api.routes` and applies CORS so the
Vite dev server at :5173 can hit the backend. The app is created via
:func:`create_app` and exported as the module-level ``app`` object that
uvicorn mounts (``uvicorn llm_lawyer.main:app``).
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from llm_lawyer import __version__
from llm_lawyer.api.routes import (
    analyses,
    audit_events,
    cases,
    chat,
    documents,
    emails,
    health,
    opposing,
    qa,
    redactions,
    relevancy,
)
from llm_lawyer.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="LLM Lawyer",
        version=__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(cases.router)
    app.include_router(emails.router)
    app.include_router(documents.router)
    app.include_router(redactions.router)
    app.include_router(analyses.router)
    app.include_router(opposing.router)
    app.include_router(qa.router)
    app.include_router(relevancy.router)
    app.include_router(audit_events.router)
    app.include_router(chat.router)

    return app


app = create_app()
