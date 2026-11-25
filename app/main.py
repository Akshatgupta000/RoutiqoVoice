"""FastAPI entry point for the Routiqo AI Sales Agent.

Run from the project folder:

    uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import logging
import re
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import database
from app.ai_agent import generate_reply, summarize_call
from app.config import STATIC_DIR, get_settings
from app.lead_service import build_fallback_summary, score_lead
from app.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    LeadCreate,
    LeadListResponse,
    LeadResponse,
    SummarizeRequest,
    SummaryResponse,
)
logger = logging.getLogger("routiqo")
MAX_BODY_BYTES = 100_000
_CONVERSATION_ID = re.compile(r"[A-Za-z0-9_-]{1,80}")


def _present_lead(row: dict) -> dict:
    """Attach a fresh score breakdown from the stored inputs.

    The saved lead_score stays as it was calculated at insert time.
    The breakdown uses the same rules, so the panel can explain the points.
    """
    scored = score_lead(
        row["vehicle_count"],
        row["business_problem"],
        row["interested_in_demo"],
        row["email"],
    )
    presented = dict(row)
    presented["score_breakdown"] = scored["score_breakdown"]
    presented["recommended_next_action"] = row["next_action"]
    return presented


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    database.init_db(settings.database_path)
    if settings.ai_configured:
        logger.info("AI mode: gemini, model=%s", settings.gemini_model)
    else:
        logger.info("AI mode: demo (%s)", settings.config_issue)
    yield


def create_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app = FastAPI(
        title="Routiqo AI Sales Agent",
        summary="Voice sales assistant prototype for Routiqo fleet dispatch.",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def limit_request_body(request, call_next):
        length = request.headers.get("content-length")
        if length:
            try:
                if int(length) > MAX_BODY_BYTES:
                    return JSONResponse(status_code=413, content={"detail": "Request is too large."})
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Invalid content length."})
        return await call_next(request)

    @app.exception_handler(Exception)
    async def unhandled_error(request, exc):
        if isinstance(exc, HTTPException):
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        logger.exception("Unhandled error")
        return JSONResponse(
            status_code=500,
            content={"detail": "Something went wrong. Please try again."},
        )

    @app.get("/", include_in_schema=False)
    def dashboard():
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/api/health", response_model=HealthResponse)
    def health():
        settings = get_settings()
        database_ok = database.ping(settings.database_path)
        return JSONResponse(
            status_code=200 if database_ok else 503,
            content=HealthResponse(
                status="ok" if database_ok else "degraded",
                demo_mode=not settings.ai_configured,
                model=settings.gemini_model or None,
                database="ok" if database_ok else "unavailable",
                config_issue=settings.config_issue,
            ).model_dump(),
        )

    @app.post("/api/chat", response_model=ChatResponse)
    def chat(payload: ChatRequest):
        settings = get_settings()
        conversation_id = payload.conversation_id or ""
        if not _CONVERSATION_ID.fullmatch(conversation_id):
            conversation_id = uuid.uuid4().hex
        history = [item.model_dump() for item in payload.conversation_history]
        result = generate_reply(settings, payload.message, history)
        return ChatResponse(
            conversation_id=conversation_id,
            response=result["response"],
            mode=result["mode"],
            knowledge_sections=result["knowledge_sections"],
            lead_hints=result["lead_hints"],
            notice=result["notice"],
        )

    @app.post("/api/leads", response_model=LeadResponse)
    def create_lead(payload: LeadCreate):
        settings = get_settings()
        scored = score_lead(
            payload.vehicle_count,
            payload.business_problem,
            payload.interested_in_demo,
            payload.email,
        )
        summary = payload.call_summary
        if not summary:
            summary = build_fallback_summary(
                customer_name=payload.customer_name,
                company_name=payload.company_name,
                vehicle_count=payload.vehicle_count,
                business_problem=payload.business_problem,
                interested_in_demo=payload.interested_in_demo,
                transcript="",
                score=scored,
            )["summary"]
        saved = database.insert_lead(
            settings.database_path,
            {
                "customer_name": payload.customer_name,
                "company_name": payload.company_name,
                "email": payload.email,
                "vehicle_count": payload.vehicle_count,
                "business_problem": payload.business_problem,
                "interested_in_demo": payload.interested_in_demo,
                "lead_score": scored["lead_score"],
                "qualification_status": scored["qualification_status"],
                "call_summary": summary,
                "next_action": scored["recommended_next_action"],
            },
        )
        return _present_lead(saved)

    @app.get("/api/leads", response_model=LeadListResponse)
    def get_leads():
        settings = get_settings()
        rows = [_present_lead(row) for row in database.list_leads(settings.database_path)]
        return {"leads": rows, "count": len(rows)}

    @app.get("/api/leads/{lead_id}", response_model=LeadResponse)
    def get_lead(lead_id: int):
        settings = get_settings()
        row = database.get_lead(settings.database_path, lead_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Lead not found.")
        return _present_lead(row)

    @app.post("/api/summarize", response_model=SummaryResponse)
    def summarize(payload: SummarizeRequest):
        settings = get_settings()
        result = summarize_call(settings, payload.model_dump())
        return result

    return app


app = create_app()
