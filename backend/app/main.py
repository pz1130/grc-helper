from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    from app.iam.router import audit_router, router as iam_router, users_router

    install_error_handlers(application)
    application.include_router(iam_router)
    application.include_router(users_router)
    application.include_router(audit_router)

    return application


app = create_app()
