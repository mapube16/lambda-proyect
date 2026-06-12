"""
rag_service.py — Per-tenant RAG (Retrieval-Augmented Generation) with Pinecone.

Architecture:
- Embeddings: text-embedding-3-small via OpenAI API (1536 dims)
- Storage: Pinecone Starter (free tier) with namespace=user_id for tenant isolation
- Chunking: RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
- Metadata: rag_documents MongoDB collection via tenant_config.save_rag_document_metadata

CRITICAL INVARIANT: Every Pinecone upsert/query uses namespace=user_id ALWAYS.
    assert user_id at the top of every public function prevents silent cross-tenant leakage.

Graceful degradation: if PINECONE_API_KEY is not set, both public functions return
    gracefully without raising an exception — allows testing and dev without real creds.
"""

import os
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from openai import AsyncOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger("cobranza.rag_service")

# ── Constants ──────────────────────────────────────────────────────────────────

EMBED_MODEL = "text-embedding-3-small"
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "cobranza-rag")
EMBED_DIMS = 1536
MAX_EMBED_CHARS = 8000  # Truncate input text before sending to OpenAI

# ── Lazy clients ───────────────────────────────────────────────────────────────

_openai_client: Optional[AsyncOpenAI] = None


def _get_openai() -> AsyncOpenAI:
    """Return (or create) the shared AsyncOpenAI client."""
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _openai_client


async def _get_pinecone_index():
    """
    Return an async Pinecone index handle, creating the index if it does not
    exist. Returns None if PINECONE_API_KEY is not configured.

    pinecone 9.x async API: the control-plane client (AsyncPinecone) exposes
    `has_index` / `create_index` / `describe_index`, but data-plane ops
    (upsert/query) require a data-plane handle built from the index HOST via
    `IndexAsyncio(host=...)`. We resolve the host with describe_index.
    """
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        return None

    from pinecone import AsyncPinecone, ServerlessSpec

    pc = AsyncPinecone(api_key=api_key)

    # Create index if not exists (control plane)
    if not await pc.has_index(PINECONE_INDEX_NAME):
        logger.info("[RAG] Creating Pinecone index: %s", PINECONE_INDEX_NAME)
        await pc.create_index(
            name=PINECONE_INDEX_NAME,
            dimension=EMBED_DIMS,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )

    # Resolve the data-plane host and return an async index handle
    desc = await pc.describe_index(PINECONE_INDEX_NAME)
    return pc.IndexAsyncio(host=desc.host)


# ── Internal helpers ───────────────────────────────────────────────────────────

async def _embed_text(text: str) -> list:
    """
    Embed text via OpenAI text-embedding-3-small.
    Truncates to MAX_EMBED_CHARS to stay within token limits.
    Returns list[float] of length EMBED_DIMS (1536).
    """
    if len(text) > MAX_EMBED_CHARS:
        text = text[:MAX_EMBED_CHARS]
    client = _get_openai()
    response = await client.embeddings.create(
        model=EMBED_MODEL,
        input=text,
    )
    return response.data[0].embedding


def _chunk_text(text: str) -> list:
    """
    Split text into semantic chunks using RecursiveCharacterTextSplitter.
    chunk_size=1000, chunk_overlap=100 per D-07/D-09 constraint.
    Returns list[str] with empty strings filtered out.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=100,
        length_function=len,
        is_separator_regex=False,
    )
    chunks = splitter.split_text(text)
    return [c for c in chunks if c.strip()]


# ── Public API ─────────────────────────────────────────────────────────────────

async def ingest_document(
    user_id: str,
    content: str,
    title: str,
    doc_type: str,
) -> dict:
    """
    Chunk, embed, and upsert a document to Pinecone under namespace=user_id.
    Also saves metadata to MongoDB rag_documents collection.

    Args:
        user_id:  Tenant identifier — used as Pinecone namespace. MUST be non-empty.
        content:  Raw document text to chunk and embed.
        title:    Human-readable document title stored in vector metadata.
        doc_type: Document type label (e.g. "pdf", "manual", "policy").

    Returns:
        {"doc_id": str, "chunk_count": int} on success.
        {"doc_id": None, "chunk_count": 0, "error": str} on graceful failure.
    """
    assert user_id, "user_id required for Pinecone namespace isolation"  # T-25-09

    # Graceful degradation when Pinecone is not configured
    if not os.getenv("PINECONE_API_KEY"):
        logger.warning("[RAG] PINECONE_API_KEY not set — skipping ingest for user %s", user_id)
        return {"doc_id": None, "chunk_count": 0, "error": "PINECONE_API_KEY not set"}

    # Chunk
    chunks = _chunk_text(content)
    if not chunks:
        logger.warning("[RAG] No chunks produced for user %s title='%s'", user_id, title)
        return {"doc_id": None, "chunk_count": 0, "error": "no chunks"}

    doc_id = str(uuid.uuid4())

    # Embed each chunk and build vector list
    vectors = []
    for i, chunk in enumerate(chunks):
        emb = await _embed_text(chunk)
        vectors.append({
            "id": f"{doc_id}_chunk_{i}",
            "values": emb,
            "metadata": {
                "user_id": user_id,
                "doc_id": doc_id,
                "title": title,
                "doc_type": doc_type,
                "chunk_index": i,
                "text": chunk[:500],  # Store preview in metadata
            },
        })

    # Upsert to Pinecone — ALWAYS namespace=user_id (T-25-09, T-25-10)
    index = await _get_pinecone_index()
    await index.upsert(vectors=vectors, namespace=user_id)
    logger.info(
        "[RAG] Upserted %d vectors for user=%s doc_id=%s title='%s'",
        len(vectors), user_id, doc_id, title,
    )

    # Persist metadata to MongoDB
    from cobranza.tenant_config import save_rag_document_metadata
    await save_rag_document_metadata(user_id, title, doc_type, len(chunks))

    return {"doc_id": doc_id, "chunk_count": len(chunks)}


async def search_knowledge(
    user_id: str,
    query: str,
    top_k: int = 5,
) -> list:
    """
    Semantic search over a tenant's RAG namespace in Pinecone.

    NEVER queries across namespaces — namespace is always locked to user_id.

    Args:
        user_id: Tenant identifier — queries ONLY this Pinecone namespace. MUST be non-empty.
        query:   Natural language query string.
        top_k:   Number of top results to return (default 5).

    Returns:
        list[dict] with keys {"text", "score", "title", "doc_type"}.
        Returns [] on missing config or empty query (no exception raised).
    """
    assert user_id, "user_id required for Pinecone namespace isolation"  # T-25-09

    # Graceful degradation when Pinecone is not configured
    if not os.getenv("PINECONE_API_KEY"):
        logger.warning("[RAG] PINECONE_API_KEY not set — returning empty results for user %s", user_id)
        return []

    if not query or not query.strip():
        return []

    index = await _get_pinecone_index()
    if index is None:
        return []

    # Embed the query
    query_vector = await _embed_text(query)

    # Query Pinecone — ALWAYS namespace=user_id (T-25-09, T-25-10)
    result = await index.query(
        vector=query_vector,
        top_k=top_k,
        namespace=user_id,
        include_metadata=True,
    )

    matches = result.get("matches", [])
    logger.info(
        "[RAG] search_knowledge user=%s query='%s' → %d matches",
        user_id, query[:60], len(matches),
    )

    return [
        {
            "text": m["metadata"].get("text", ""),
            "score": m["score"],
            "title": m["metadata"].get("title", ""),
            "doc_type": m["metadata"].get("doc_type", ""),
        }
        for m in matches
    ]
