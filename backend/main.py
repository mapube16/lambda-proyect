"""
Lambda Office — FastAPI entry point.
All route logic lives in routers/. All shared state lives in state.py.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S")
for _log in ("hive_adapter", "hive_llm", "hive_tools", "hive_graph", "framework.graph.event_loop_node", "framework.graph.executor", "wa_handler"):
    logging.getLogger(_log).setLevel(logging.INFO)

import pathlib
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from database import init_db, seed_users
from security_headers import SecurityHeadersMiddleware
from landa.scheduler import start_scheduler, shutdown_scheduler
import state

from routers import auth, leads, prospect, staff, onboarding, knowledge, whatsapp, secop, agents_legacy, misc, landa


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    if os.getenv("ENABLE_SEED_USERS", "false").lower() == "true":
        from auth import hash_password as _hash
        logging.warning("DEVELOPMENT MODE: Seeding default users.")
        await seed_users([
            {"email": "staff@lambda.com",          "hashed_password": _hash("lambda2026"),  "role": "staff"},
            {"email": "dpg.seguros@gmail.com",     "hashed_password": _hash("seguros2026"), "role": "client"},
            {"email": "demo.cobranza@empresa.com", "hashed_password": _hash("demo2026"),    "role": "client"},
        ])

    from auth import hash_password as _hash
    await seed_users([
        {"email": "staff@lambda.com",          "hashed_password": _hash("lambda2026"),  "role": "staff"},
        {"email": "dpg.seguros@gmail.com",     "hashed_password": _hash("seguros2026"), "role": "client"},
        {"email": "demo.cobranza@empresa.com", "hashed_password": _hash("demo2026"),    "role": "client"},
    ])

    from orchestrator import HiveOrchestrator
    from hive_adapter import HiveAdapter
    from models import AgentRole

    async def _noop(_uid: str, _msg: dict) -> None:
        pass

    state.orchestrator = HiveOrchestrator(os.getenv("OPENAI_API_KEY", "demo-key"))
    state.orchestrator.set_broadcast_callback(_noop)
    await state.orchestrator.load_agents_from_db()

    if not state.orchestrator.get_all_agents():
        for name, role in [("Investigadora", AgentRole.RESEARCHER), ("Prospector", AgentRole.PLANNER), ("Redactora", AgentRole.WRITER), ("Analista", AgentRole.REVIEWER)]:
            await state.orchestrator.create_agent(name=name, role=role)

    state.hive_adapter = HiveAdapter(send_to_user_callback=_noop)

    from arq_pool import create_arq_pool
    state.arq_pool = await create_arq_pool()
    logging.info("ARQ pool connected.")

    await start_scheduler()
    from landa.scheduler import scheduler as _sched
    from cobranza.campaign_scheduler import register_cobranza_jobs
    register_cobranza_jobs(_sched)

    logging.info("Lambda Office started!")
    yield
    if state.arq_pool is not None:
        await state.arq_pool.aclose()
    shutdown_scheduler()
    logging.info("Shutting down.")


app = FastAPI(title="Lambda Office", version="1.0.0", lifespan=lifespan)

_MAX_BODY_BYTES = int(os.getenv("MAX_REQUEST_BYTES", "2000000"))
_EXEMPT_BODY_LIMIT_PATHS = ("/api/staff/clients/",)


@app.middleware("http")
async def limit_request_body(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if request.method in {"POST", "PUT", "PATCH"} and content_length:
        path = request.url.path
        if path.startswith(_EXEMPT_BODY_LIMIT_PATHS) and "knowledge/upload" in path:
            return await call_next(request)
        try:
            if int(content_length) > _MAX_BODY_BYTES:
                return JSONResponse({"detail": "Request body too large"}, status_code=413)
        except ValueError:
            return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)
    return await call_next(request)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logging.error("[unhandled] %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse({"detail": "Internal server error"}, status_code=500)

ALLOWED_ORIGINS = list(set([
    "http://localhost:5173",
    "http://localhost:3000",
    os.getenv("FRONTEND_URL", "http://localhost:5173"),
]))

app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_credentials=True, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"], allow_headers=["Content-Type", "Authorization"])
app.add_middleware(SecurityHeadersMiddleware)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(misc.router)
app.include_router(auth.router)
app.include_router(leads.router)
app.include_router(prospect.router)
app.include_router(staff.router)
app.include_router(onboarding.router)
app.include_router(knowledge.router)
app.include_router(whatsapp.router)
app.include_router(secop.router)
app.include_router(agents_legacy.router)
app.include_router(landa.router)


# ── Cobranza (separate product) ───────────────────────────────────────────────
from cobranza.router import router as cobranza_router
from cobranza.webhooks import vapi_router as _vapi_router
from cobranza.voice_router import router as voice_router
app.include_router(cobranza_router)
app.include_router(_vapi_router)
app.include_router(voice_router)

# ── Static frontend (must be last) ───────────────────────────────────────────
_frontend_dist = pathlib.Path(__file__).parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)