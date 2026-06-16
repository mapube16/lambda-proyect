import os
import logging
import hashlib
import asyncio
from typing import List
from urllib.parse import urlparse, urlunparse

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel, Field

from auth import require_staff
from database import get_knowledge_sources, delete_knowledge_source, delete_knowledge_by_user

router = APIRouter()


class UrlIngestRequest(BaseModel):
    user_id: str | None = None
    url: str | None = None
    urls: list[str] = Field(default_factory=list)
    source_type: str = "url_empresa"


@router.post("/api/staff/clients/{client_id}/knowledge/upload")
async def upload_knowledge_docs(
    client_id: str,
    files: List[UploadFile] = File(...),
    _staff: dict = Depends(require_staff),
):
    from rag import extract_text, ingest_document
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")
    results = []
    for file in files:
        file_bytes = await file.read()
        if not file_bytes:
            results.append({"filename": file.filename, "error": "empty file"})
            continue
        try:
            text = extract_text(file_bytes, file.filename or "upload", file.content_type or "")
        except Exception as e:
            results.append({"filename": file.filename, "error": str(e)})
            continue
        if not text.strip():
            results.append({"filename": file.filename, "error": "no readable text"})
            continue
        chunk_count = await ingest_document(user_id=client_id, text=text, filename=file.filename or "upload", source_type="file")
        results.append({"filename": file.filename, "chunks_stored": chunk_count})
    return results


@router.post("/api/staff/clients/{client_id}/knowledge/url")
async def ingest_knowledge_url(client_id: str, request: UrlIngestRequest, _staff: dict = Depends(require_staff)):
    from rag import fetch_url_text, ingest_document
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")
    source_type = (request.source_type or "url_empresa").strip().lower()
    if source_type not in {"url_empresa", "url_competencia", "url"}:
        raise HTTPException(status_code=422, detail="source_type invalido")
    urls: list[str] = []
    if request.url and request.url.strip():
        urls.append(request.url.strip())
    urls.extend([u.strip() for u in (request.urls or []) if isinstance(u, str) and u.strip()])
    deduped_urls = list(dict.fromkeys(urls))
    if not deduped_urls:
        raise HTTPException(status_code=422, detail="Debes enviar al menos una URL")

    def canonicalize_url(raw: str) -> str:
        parsed = urlparse(raw)
        return urlunparse(parsed._replace(query="", fragment=""))

    def build_filename(raw_url: str) -> str:
        canonical = canonicalize_url(raw_url)
        parsed = urlparse(canonical)
        host = (parsed.netloc or "url").replace(":", "_")
        path = (parsed.path or "/").strip("/").replace("/", "_")
        base = f"{host}__{path}" if path else host
        digest = hashlib.sha1(raw_url.encode("utf-8")).hexdigest()[:10]
        return f"{base[:140]}__{digest}"

    results = []
    for target_url in deduped_urls:
        try:
            async with asyncio.timeout(30):
                text = await fetch_url_text(target_url)
        except Exception as e:
            results.append({"url": target_url, "error": f"Cannot fetch URL: {e}"})
            continue
        if not text.strip():
            results.append({"url": target_url, "error": "No readable text found at URL"})
            continue
        filename = build_filename(target_url)
        try:
            async with asyncio.timeout(60):
                chunk_count = await ingest_document(user_id=client_id, text=text, filename=filename, source_type=source_type)
        except TimeoutError:
            results.append({"url": target_url, "error": "Ingest timed out"})
            continue
        results.append({"url": target_url, "url_canonical": canonicalize_url(target_url), "filename": filename, "source_type": source_type, "chunks_stored": chunk_count})

    stored = [r for r in results if not r.get("error")]
    if not stored:
        first_error = results[0].get("error") if results else "No se pudo procesar ninguna URL"
        raise HTTPException(status_code=422, detail=first_error)
    return {"total_urls": len(deduped_urls), "stored_urls": len(stored), "results": results}


@router.get("/api/staff/clients/{client_id}/knowledge")
async def get_knowledge_sources_endpoint(client_id: str, _staff: dict = Depends(require_staff)):
    return await get_knowledge_sources(client_id)


@router.delete("/api/staff/clients/{client_id}/knowledge/{filename}")
async def delete_knowledge_source_endpoint(client_id: str, filename: str, _staff: dict = Depends(require_staff)):
    return {"deleted_chunks": await delete_knowledge_source(client_id, filename)}


@router.delete("/api/staff/clients/{client_id}/knowledge")
async def clear_knowledge_endpoint(client_id: str, _staff: dict = Depends(require_staff)):
    return {"deleted_chunks": await delete_knowledge_by_user(client_id)}
