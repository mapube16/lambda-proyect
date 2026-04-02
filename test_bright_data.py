#!/usr/bin/env python3
"""Test Bright Data Web Scraper integration."""
import requests
import json

BASE_URL = "https://my.landatech.org"

# Step 1: Login to get token
print("🔐 Logging in...")
login_resp = requests.post(
    f"{BASE_URL}/auth/login",
    json={
        "email": "dpg.seguros@gmail.com",
        "password": "seguros2026"
    }
)

if login_resp.status_code != 200:
    print(f"❌ Login failed: {login_resp.text}")
    exit(1)

token = login_resp.json().get("access_token")
print(f"✅ Login successful. Token: {token[:20]}...")

# Step 2: Call prospecting with Bright Data
print("\n🚀 Starting prospecting with Bright Data Web Scraper...")
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

payload = {
    "campaign": {
        "industria": "construcción",
        "ciudad": "Bogotá"
    },
    "max_results": 5,
    "source_priority": "bright_data"  # ← ACTIVATE BRIGHT DATA
}

prospect_resp = requests.post(
    f"{BASE_URL}/api/prospect",
    json=payload,
    headers=headers
)

if prospect_resp.status_code != 200:
    print(f"❌ Prospecting failed: {prospect_resp.text}")
    exit(1)

print(f"✅ Prospecting started!")
print(f"Response: {json.dumps(prospect_resp.json(), indent=2, ensure_ascii=False)}")
print("\n📊 Check Railway logs to see Bright Data Web Scraper in action!")
print("   Look for: [Bright Data Web] in the logs")
