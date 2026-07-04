"""
demo_app.py — LOCAL demo backend (NO es para producción).

App FastAPI mínima para ver el panel de Cobranza sin arrancar el pipeline de voz
(pipecat). Incluye solo auth + cobranza + softseguros/debtors, apuntando al mismo
Mongo Atlas. Levantar con:  uvicorn demo_app:app --port 8001
"""
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv(".env")

import certifi
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient

import database


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializa el cliente Mongo global (lo que hace el lifespan real de main.py).
    database._client = AsyncIOMotorClient(os.getenv("MONGODB_URI"), tlsCAFile=certifi.where())
    yield
    database._client.close()


app = FastAPI(title="Cobranza demo (local)", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:5174", "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers ligeros (ninguno importa pipecat/voz).
from routers import auth as _auth_routes   # login/me
from cobranza.router import router as cobranza_router
from routes.debtors import router as debtors_router

app.include_router(_auth_routes.router)
for _name in ("misc", "staff"):
    try:
        _m = __import__(f"routers.{_name}", fromlist=["router"])
        app.include_router(_m.router)
    except Exception as _e:  # noqa: BLE001 — routers opcionales para el demo
        print(f"[demo_app] skip router {_name}: {type(_e).__name__}")
app.include_router(cobranza_router)
app.include_router(debtors_router)


@app.get("/")
def root():
    return {"ok": True, "demo": "cobranza", "note": "backend local mínimo"}
