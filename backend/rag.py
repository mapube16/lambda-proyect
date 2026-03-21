"""
rag.py — Per-client RAG (Retrieval-Augmented Generation).

Architecture:
- Embeddings: text-embedding-3-small via OpenAI API (~$0.00002/1k tokens)
- Storage: MongoDB collection `client_knowledge` (chunks + embedding vectors as float arrays)
- Retrieval: cosine similarity computed in Python (no Atlas Vector Search required)
- Supported sources: PDF (PyMuPDF), DOCX (python-docx), plain text, URL (httpx)
"""

import math
import os
import logging
from typing import Optional

logger = logging.getLogger("rag")

EMBED_MODEL = "text-embedding-3-small"
CHUNK_SIZE = 600       # characters per chunk
CHUNK_OVERLAP = 80     # overlap between consecutive chunks


# ── Text extraction ────────────────────────────────────────────────────────────

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract plain text from a PDF binary blob using PyMuPDF."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        pages = []
        for page in doc:
            text = page.get_text()
            if text.strip():
                pages.append(text)
        return "\n\n".join(pages)
    except ImportError:
        raise RuntimeError("PyMuPDF not installed. Run: pip install pymupdf")


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract plain text from a DOCX binary blob."""
    try:
        import io
        from docx import Document
        doc = Document(io.BytesIO(file_bytes))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)
    except ImportError:
        raise RuntimeError("python-docx not installed. Run: pip install python-docx")


async def fetch_url_text(url: str) -> str:
    """Fetch a URL and return stripped plain text (max 20k chars)."""
    import re
    import httpx
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        html = resp.text
    # Strip HTML tags
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:20_000]


def extract_text(
    file_bytes: bytes,
    filename: str,
    content_type: str = "",
) -> str:
    """Dispatch text extraction based on filename extension or content-type."""
    name_lower = filename.lower()
    if name_lower.endswith(".pdf") or "pdf" in content_type:
        return extract_text_from_pdf(file_bytes)
    if name_lower.endswith(".docx") or "wordprocessingml" in content_type:
        return extract_text_from_docx(file_bytes)
    # Fall back to treating bytes as UTF-8 text
    return file_bytes.decode("utf-8", errors="replace")


# ── Chunking ───────────────────────────────────────────────────────────────────

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks by character count."""
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = end - overlap
    return chunks


# ── Embeddings ─────────────────────────────────────────────────────────────────

async def embed_text(text: str) -> list[float]:
    """Embed a single text string using OpenAI text-embedding-3-small."""
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = await client.embeddings.create(
        model=EMBED_MODEL,
        input=text[:8_000],
    )
    return response.data[0].embedding


async def embed_texts_batch(texts: list[str], batch_size: int = 512) -> list[list[float]]:
    """
    Embed multiple texts in batch, dramatically reducing API calls.
    OpenAI allows up to 2048 inputs per request; we use 512 as safe batch size.
    Returns embeddings in the same order as input texts.
    """
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = [t[:8_000] for t in texts[i:i + batch_size]]
        response = await client.embeddings.create(model=EMBED_MODEL, input=batch)
        # API returns embeddings in the same order as input
        all_embeddings.extend(item.embedding for item in response.data)
    return all_embeddings


# ── Similarity ─────────────────────────────────────────────────────────────────

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Pure-Python cosine similarity (no numpy required)."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


# ── Ingest ─────────────────────────────────────────────────────────────────────

async def ingest_document(
    user_id: str,
    text: str,
    filename: str,
    source_type: str,  # "pdf" | "docx" | "text" | "url"
) -> int:
    """
    Chunk + embed + persist document for a client.
    Returns the number of chunks stored.
    Idempotent per filename: deletes old chunks before inserting.
    """
    from database import save_knowledge_chunk, delete_knowledge_source

    # Remove previous version of this file (re-upload)
    await delete_knowledge_source(user_id, filename)

    chunks = [c for c in chunk_text(text) if c.strip()]
    if not chunks:
        return 0

    # Embed all chunks in a single batch API call (was: one call per chunk)
    try:
        embeddings = await embed_texts_batch(chunks)
    except Exception as e:
        logger.error(f"[rag] Batch embedding failed for '{filename}': {e}")
        return 0

    stored = 0
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        try:
            await save_knowledge_chunk(
                user_id=user_id,
                chunk_text=chunk,
                embedding=embedding,
                filename=filename,
                source_type=source_type,
                chunk_index=i,
            )
            stored += 1
        except Exception as e:
            logger.warning(f"[rag] Failed to save chunk {i} of '{filename}': {e}")

    logger.info(f"[rag] Ingested {stored}/{len(chunks)} chunks from '{filename}' for user {user_id}")
    return stored


# ── Retrieval ──────────────────────────────────────────────────────────────────

async def query_rag(user_id: str, query: str, top_k: int = 5) -> str:
    """
    Embed the query, rank all user chunks by cosine similarity,
    return top-k as a context string ready for LLM injection.
    Returns empty string if no knowledge base exists.
    """
    from database import get_knowledge_chunks

    chunks = await get_knowledge_chunks(user_id)
    if not chunks:
        return ""

    query_vec = await embed_text(query)

    scored: list[tuple[float, str, str, str]] = []
    for doc in chunks:
        vec = doc.get("embedding") or []
        if vec:
            sim = cosine_similarity(query_vec, vec)
            scored.append((
                sim,
                doc["chunk_text"],
                doc.get("filename", ""),
                doc.get("source_type", "desconocido"),
            ))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]

    parts = []
    for _sim, text, fname, source_type in top:
        parts.append(f"[{source_type}] [{fname}]\n{text}")

    return "\n\n---\n\n".join(parts)


async def get_all_knowledge_text(user_id: str, max_chars: int = 12_000) -> str:
    """
    Return a condensed concatenation of all knowledge chunks for the user.
    Used by the queen proposal (full context, not similarity search).
    Truncated to max_chars to fit LLM context window.
    """
    from database import get_knowledge_chunks

    chunks = await get_knowledge_chunks(user_id)
    if not chunks:
        return ""

    source_labels = {
        "url_empresa": "EMPRESA_CLIENTE",
        "url_competencia": "COMPETENCIA",
        "conversation": "TRANSCRIPCION_REUNION",
        "file": "DOCUMENTO_CLIENTE",
        "url": "URL_REFERENCIA",
    }

    def classify_bucket(source_type: str, filename: str) -> str:
        st = (source_type or "").lower()
        fn = (filename or "").lower()

        if st in ("url_competencia",):
            return "competencia"
        if st in ("conversation", "url_empresa"):
            return "empresa"
        if st in ("file", "url", "url_referencia"):
            # Heuristic: if filename explicitly says competitor, treat as competitor.
            if any(k in fn for k in ("compet", "competidor", "benchmark", "rival")):
                return "competencia"
            return "empresa"
        return "otros"

    # Group by (source_type, filename), keeping chunk order
    by_file: dict[tuple[str, str], list[tuple[int, str]]] = {}
    for doc in chunks:
        source_type = str(doc.get("source_type", "desconocido"))
        fname = doc.get("filename", "documento")
        chunk_index = int(doc.get("chunk_index", 0) or 0)
        by_file.setdefault((source_type, fname), []).append((chunk_index, doc["chunk_text"]))

    section_empresa: list[str] = []
    section_competencia: list[str] = []
    section_otros: list[str] = []

    for (source_type, fname), indexed_texts in by_file.items():
        indexed_texts.sort(key=lambda x: x[0])
        content = " ".join(t for _, t in indexed_texts)
        source_label = source_labels.get(source_type, source_type.upper())
        block = f"=== [{source_label}] {fname} ===\n{content}"
        bucket = classify_bucket(source_type, fname)
        if bucket == "empresa":
            section_empresa.append(block)
        elif bucket == "competencia":
            section_competencia.append(block)
        else:
            section_otros.append(block)

    # Deterministic hierarchy budget: empresa dominates, competencia is low-priority.
    empresa_budget = int(max_chars * 0.68)
    otros_budget = int(max_chars * 0.20)
    competencia_budget = max_chars - empresa_budget - otros_budget

    empresa_text = "\n\n".join(section_empresa)[:empresa_budget]
    otros_text = "\n\n".join(section_otros)[:otros_budget]
    competencia_text = "\n\n".join(section_competencia)[:competencia_budget]

    full = (
        "### PRIORIDAD_1_EMPRESA_CLIENTE (fuente principal para identidad/campaña)\n"
        f"{empresa_text}\n\n"
        "### PRIORIDAD_2_OTRAS_FUENTES\n"
        f"{otros_text}\n\n"
        "### PRIORIDAD_3_COMPETENCIA (solo benchmark, no identidad)\n"
        f"{competencia_text}"
    )
    return full[:max_chars]
