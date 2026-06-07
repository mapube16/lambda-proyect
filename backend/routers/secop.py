from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth import get_current_user

router = APIRouter()


class NitEnrichRequest(BaseModel):
    nit: str


class RadarRequest(BaseModel):
    sector: str
    ciudad: Optional[str] = None
    max_procesos: int = 10
    max_proponentes: int = 20


@router.post("/api/secop/enrich-nit")
async def enrich_nit_endpoint(request: NitEnrichRequest, current_user: dict = Depends(get_current_user)):
    from nit_enricher import enrich_nit
    return await enrich_nit(request.nit)


@router.post("/api/secop/radar-polizas")
async def radar_polizas_endpoint(request: RadarRequest, current_user: dict = Depends(get_current_user)):
    from secop_radar import build_poliza_leads
    return await build_poliza_leads(keyword=request.sector, ciudad=request.ciudad, max_procesos=request.max_procesos, max_proponentes=request.max_proponentes)


@router.get("/api/secop/procesos-abiertos")
async def procesos_abiertos_endpoint(sector: str, ciudad: Optional[str] = None, limit: int = 20, current_user: dict = Depends(get_current_user)):
    from secop_radar import fetch_open_processes
    return await fetch_open_processes(sector, ciudad, limit)
