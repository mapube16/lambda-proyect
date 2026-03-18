import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from main import app

@pytest_asyncio.fixture
async def async_client():
    """Async test client for FastAPI app. Uses in-process transport — no network required."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
