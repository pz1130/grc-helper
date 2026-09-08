from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401  — 注册全部模型，跨模块外键才解析得了
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title="GRC Helper", version=settings.app_version)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": settings.app_version}

    from app.errors import install_error_handlers
    from app.indexing.router import router as index_router
    from app.ingest.router import router as documents_router
    from app.iam.router import audit_router, router as iam_router, users_router
    from app.llm.router import router as settings_router
    from app.search.router import router as search_router

    install_error_handlers(application)
    application.include_router(iam_router)
    application.include_router(users_router)
    application.include_router(audit_router)
    application.include_router(settings_router)
    application.include_router(documents_router)
    application.include_router(search_router)
    application.include_router(index_router)

    return application


app = create_app()
