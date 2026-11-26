from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.database import init_db, make_engine
from app.routers import web
from app.services.scanner import Scanner


def create_app(
    settings: Settings | None = None, *, feed_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        engine = make_engine(config.database_url)
        try:
            await init_db(engine)
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            application.state.sessions = sessions
            async with httpx.AsyncClient(
                timeout=10, follow_redirects=True, max_redirects=3, transport=feed_transport,
            ) as client:
                scanner = Scanner(sessions, client)
                application.state.scanner = scanner
                scheduler = AsyncIOScheduler(timezone="UTC")
                scheduler.add_job(
                    scanner.scan, "interval", minutes=config.scan_interval_minutes,
                    max_instances=1, coalesce=True,
                )
                scheduler.start()
                try:
                    yield
                finally:
                    scheduler.pause()
                    async with scanner.lock:
                        scheduler.shutdown(wait=False)
        finally:
            await engine.dispose()

    application = FastAPI(title="FeedWatch Starter", lifespan=lifespan)

    @application.middleware("http")
    async def browser_origin_guard(request: Request, call_next):
        if request.method == "POST":
            origin = request.headers.get("origin")
            cross_site = request.headers.get("sec-fetch-site") == "cross-site"
            if cross_site or (origin and origin.rstrip("/") != str(request.base_url).rstrip("/")):
                return JSONResponse({"detail": "Cross-site requests are blocked."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @application.get("/health")
    async def health(request: Request):
        async with request.app.state.sessions() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ok"}

    application.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
    application.include_router(web.router)
    return application


app = create_app()
