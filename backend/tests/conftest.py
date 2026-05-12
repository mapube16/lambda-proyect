import os
# Phase 18: ensure SOFTSEGUROS Fernet key is set before any softseguros module is imported.
os.environ.setdefault(
    "SOFTSEGUROS_ENCRYPTION_KEY",
    "zmWmHEnQ7E5jXk9V2bN4qY7tR1xL0pUaG3sH6vN8cZ4=",  # test-only key (valid Fernet)
)

import pytest
import pytest_asyncio
import database
from mongomock_motor import AsyncMongoMockClient
from httpx import AsyncClient, ASGITransport
from main import app


@pytest_asyncio.fixture(autouse=True)
async def reset_db():
    """Fresh in-memory MongoDB mock per test — no real Atlas connection needed."""
    mock_client = AsyncMongoMockClient()
    await database.init_db(client=mock_client)
    yield
    # Drop users collection directly (avoids sync list_collection_names call)
    await database.get_db().users.drop()


@pytest_asyncio.fixture
async def async_client():
    """Async test client for FastAPI app. Uses in-process transport — no network required."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
