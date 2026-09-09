from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models
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

    from app.controls.router import router as controls_router
    from app.errors import install_error_handlers
    from app.extraction.router import router as extraction_router
    from app.iam.router import audit_router, users_router
    from app.iam.router import router as iam_router
    from app.indexing.router import router as index_router
    from app.ingest.router import router as documents_router
    from app.llm.router import router as settings_router
    from app.matrix.router import router as matrix_router
    from app.frameworks.router import router as frameworks_router
    from app.mapping.router import router as mapping_router
    from app.review.router import router as review_router
    from app.search.router import router as search_router

    install_error_handlers(application)
    application.include_router(iam_router)
    application.include_router(users_router)
    application.include_router(audit_router)
    application.include_router(settings_router)
    application.include_router(documents_router)
    application.include_router(search_router)
    application.include_router(index_router)
    application.include_router(controls_router)
    application.include_router(extraction_router)
    application.include_router(matrix_router)
    application.include_router(review_router)
    application.include_router(frameworks_router)
    application.include_router(mapping_router)

    return application


app = create_app()
