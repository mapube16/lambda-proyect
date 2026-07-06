"""
Lambda Office — FastAPI entry point.
All route logic lives in routers/. All shared state lives in state.py.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
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
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from database import init_db, seed_users
from security_headers import SecurityHeadersMiddleware
from landa.scheduler import start_scheduler, shutdown_scheduler
import state

from routers import auth, leads, prospect, staff, onboarding, knowledge, whatsapp, secop, agents_legacy, misc, landa


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await asyncio.wait_for(init_db(), timeout=30)
    except asyncio.TimeoutError:
        logging.warning("init_db() timeout — MongoDB may be slow")

    if os.getenv("ENABLE_SEED_USERS", "false").lower() == "true":
        from auth import hash_password as _hash
        logging.warning("DEVELOPMENT MODE: Seeding default users.")
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
    from cobranza.report_scheduler import register_report_jobs
    register_report_jobs(_sched)

    # Phase 18: SOFTSEGUROS daily sync scheduler (must run after init_db).
    try:
        from softseguros.scheduler import setup_scheduler as setup_softseguros_scheduler
        await setup_softseguros_scheduler(app)
    except Exception:  # noqa: BLE001 — scheduler must never block app startup
        logging.exception("Failed to start SOFTSEGUROS scheduler")

    # ── Kill the 1.5s-per-call voice latency (SSL context caching) ───────────
    # ROOT CAUSE (profiled): constructing GeminiLiveLLMService costs ~1.5s EVERY
    # call — not a one-time import. google.genai's client __init__ builds 3 SSL
    # contexts (httpx + websocket + aiohttp), and ssl load_verify_locations
    # (reading the CA bundle from disk) is ~0.6s × 3. The CA bundle is identical
    # every time, so we cache ssl.create_default_context by args. Effect (measured):
    # first construct ~600ms, every subsequent construct ~2ms.
    try:
        import ssl as _ssl
        _orig_ssl_ctx = _ssl.create_default_context
        _ssl_ctx_cache: dict = {}

        def _cached_ssl_ctx(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())) if kwargs else ())
            ctx = _ssl_ctx_cache.get(key)
            if ctx is None:
                ctx = _orig_ssl_ctx(*args, **kwargs)
                _ssl_ctx_cache[key] = ctx
            return ctx

        _ssl.create_default_context = _cached_ssl_ctx  # type: ignore[assignment]
        logging.info("SSL default-context cache installed (voice latency fix).")
    except Exception:  # noqa: BLE001 — never block boot
        logging.exception("SSL context cache install failed (non-fatal)")

    # ── Warm up the Gemini Live voice SDK (latency) ──────────────────────────
    # Pay the first (uncached) SSL-context build here at boot, so the first real
    # call already hits the warm ~2ms path instead of ~600ms.
    try:
        import os as _os
        from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService as _GLS
        import google.genai.types as _ggt  # noqa: F401 — force the heavy import now
        from pipecat.adapters.schemas.tools_schema import ToolsSchema as _TS  # noqa: F401
        _warm = _GLS(api_key=_os.getenv("GOOGLE_API_KEY") or "warmup", model="models/gemini-3.1-flash-live-preview")
        del _warm
        logging.info("Gemini Live voice SDK warmed up.")
    except Exception:  # noqa: BLE001 — warmup is best-effort, never block boot
        logging.exception("Gemini Live warmup failed (non-fatal)")

    logging.info("Lambda Office started!")
    yield
    if state.arq_pool is not None:
        await state.arq_pool.aclose()
    shutdown_scheduler()
    try:
        from softseguros.scheduler import shutdown_scheduler as shutdown_softseguros_scheduler
        shutdown_softseguros_scheduler(app)
    except Exception:  # noqa: BLE001
        pass
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


# Declared after limit_request_body so it executes first (outermost @middleware).
# Responds to CORS preflights before auth dependencies can reject them.
@app.middleware("http")
async def fast_options_handler(request: Request, call_next):
    if request.method == "OPTIONS":
        origin = request.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS:
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                    "Access-Control-Allow-Credentials": "true",
                    "Access-Control-Max-Age": "86400",
                },
            )
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

app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_credentials=True, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"], allow_headers=["Content-Type", "Authorization", "ngrok-skip-browser-warning"])
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

# ── Phase 25: Multi-tenant admin API ──────────────────────────────────────────
from routers.tenant_admin import router as tenant_admin_router
app.include_router(tenant_admin_router)

# ── Phase 18: SOFTSEGUROS debtors REST API ───────────────────────────────────
from routes.debtors import router as debtors_router
app.include_router(debtors_router)

# ── Static frontend (must be last) ───────────────────────────────────────────
_frontend_dist = pathlib.Path(__file__).parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)