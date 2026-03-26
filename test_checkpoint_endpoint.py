import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

# Set up in-memory MongoDB mock BEFORE importing main
import database
from mongomock_motor import AsyncMongoMockClient

async def test():
    # Initialize mock DB
    mock_client = AsyncMongoMockClient()
    await database.init_db(client=mock_client)
    
    # NOW import app
    from main import app
    from httpx import AsyncClient, ASGITransport
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Register
        r = await client.post("/auth/register", json={"email": "test@test.com", "password": "pass123"})
        print(f"✓ Register: {r.status_code}")
        
        # Login
        r = await client.post("/auth/login", json={"email": "test@test.com", "password": "pass123"})
        print(f"✓ Login: {r.status_code}")
        token = r.json()["access_token"]
        print(f"  Token: {token[:20]}...")
        
        # Try GET /api/leads/checkpoint
        r = await client.get(
            "/api/leads/checkpoint",
            headers={"Authorization": f"Bearer {token}"}
        )
        print(f"✓ GET /api/leads/checkpoint: {r.status_code}")
        if r.status_code == 200:
            print(f"  Response: {r.json()}")
        else:
            print(f"  Error: {r.text[:200]}")

asyncio.run(test())
