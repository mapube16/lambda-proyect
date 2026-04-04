#!/usr/bin/env python3
"""
test_bright_data.py — Quick test for Bright Data API connectivity.

Run this to verify your Bright Data API key and endpoints are working.
"""
import os
import asyncio
import httpx
import json

async def test_bright_data_serp():
    """Test Bright Data SERP API endpoint."""
    api_key = os.getenv("BRIGHT_DATA_API_KEY", "")

    if not api_key:
        print("❌ BRIGHT_DATA_API_KEY not set in environment")
        return False

    print(f"ℹ️  BRIGHT_DATA_API_KEY is set (length={len(api_key)})")

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            print("\n🔍 Testing SERP API endpoint...")
            resp = await client.post(
                "https://api.brightdata.com/datasets/geos/parse",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "dataset": "serp",
                    "query": "logística bogotá empresa",
                    "country": "CO",
                    "language": "es",
                    "num": 5,
                },
                timeout=15,
            )

            print(f"   Status: {resp.status_code}")

            if resp.status_code == 401:
                print("   ❌ 401 Unauthorized — API key is invalid or expired")
                return False
            elif resp.status_code == 403:
                print("   ❌ 403 Forbidden — SERP dataset not configured in dashboard")
                print("   💡 Create a SERP dataset in Bright Data dashboard first")
                return False
            elif resp.status_code == 200:
                data = resp.json()
                print(f"   ✅ 200 OK — API working!")
                print(f"   Response: {json.dumps(data, indent=2)[:500]}...")
                return True
            else:
                print(f"   ⚠️  Unexpected status: {resp.status_code}")
                print(f"   Response: {resp.text[:500]}")
                return False

        except Exception as e:
            print(f"   ❌ Error: {e}")
            return False

async def test_bright_data_web_scraper():
    """Test Bright Data Web Scraper API endpoint."""
    api_key = os.getenv("BRIGHT_DATA_API_KEY", "")

    if not api_key:
        return False

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            print("\n🔍 Testing Web Scraper API endpoint...")
            resp = await client.post(
                "https://api.brightdata.com/datasets/geos/parse",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "dataset": "web_scraper",
                    "url": "https://www.directorio.com.co/empresas/logistica/bogota",
                    "selector": "empresa",
                    "fields": ["name", "email", "phone"],
                    "limit": 5,
                },
                timeout=30,
            )

            print(f"   Status: {resp.status_code}")

            if resp.status_code == 401:
                print("   ❌ 401 Unauthorized")
                return False
            elif resp.status_code == 403:
                print("   ❌ 403 Forbidden — Web Scraper dataset not configured")
                print("   💡 Create a Web Scraper dataset in Bright Data dashboard first")
                return False
            elif resp.status_code == 200:
                data = resp.json()
                print(f"   ✅ 200 OK — Web Scraper working!")
                print(f"   Response: {json.dumps(data, indent=2)[:500]}...")
                return True
            else:
                print(f"   ⚠️  Status: {resp.status_code}")
                print(f"   Response: {resp.text[:500]}")
                return False

        except Exception as e:
            print(f"   ❌ Error: {e}")
            return False

async def main():
    print("=" * 70)
    print("BRIGHT DATA API TEST")
    print("=" * 70)

    serp_ok = await test_bright_data_serp()
    web_ok = await test_bright_data_web_scraper()

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"SERP API:        {'✅ OK' if serp_ok else '❌ FAILED'}")
    print(f"Web Scraper:     {'✅ OK' if web_ok else '❌ FAILED'}")
    print("\nIf both failed:")
    print("  1. Verify BRIGHT_DATA_API_KEY in .env")
    print("  2. Check that datasets are created in Bright Data dashboard")
    print("  3. Ensure datasets are active and have quota remaining")

if __name__ == "__main__":
    asyncio.run(main())
