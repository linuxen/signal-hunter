from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Keyword, Match
from app.services.feeds import FEEDS
from app.services.onboarding import add_keyword

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")
Session = Annotated[AsyncSession, Depends(get_session)]


async def render_dashboard(request: Request, session: AsyncSession, *, feedback: str = ""):
    keywords = (await session.scalars(select(Keyword).order_by(Keyword.folded))).all()
    matches = (
        await session.execute(
            select(Match, Keyword.term).join(Keyword).order_by(Match.id.desc()).limit(100)
        )
    ).all()
    is_htmx = request.headers.get("HX-Request") == "true"
    return templates.TemplateResponse(
        request=request,
        name="partials/dashboard_content.html" if is_htmx else "dashboard.html",
        context={
            "keywords": keywords,
            "matches": matches,
            "feeds": FEEDS,
            "feedback": feedback,
            "scan_result": request.app.state.scanner.last_result,
        },
        headers={"Vary": "HX-Request"},
    )


@router.get("/", name="dashboard")
async def dashboard(request: Request, session: Session):
    return await render_dashboard(request, session)


@router.post("/keywords", name="create_keyword")
async def create_keyword(request: Request, session: Session, keyword: Annotated[str, Form()] = ""):
    feedback = await add_keyword(session, keyword)
    return await render_dashboard(request, session, feedback=feedback)


@router.post("/scan", name="scan_feeds")
async def scan_feeds(request: Request, session: Session):
    await request.app.state.scanner.scan()
    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(request.url_for("dashboard"), status_code=303)
    return await render_dashboard(request, session)
