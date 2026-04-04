#!/usr/bin/env python3
"""
Quick test script to verify voice orchestrator configuration.

Usage:
    python test_voice_config.py

Checks:
    ✓ ASSEMBLY_AI_API_KEY is set
    ✓ GOOGLE_CLOUD_TTS credentials are valid
    ✓ Twilio config is set
    ✓ OPENAI_API_KEY is set
"""
import os
import sys
import base64
import json
from pathlib import Path

def check_env_var(name: str, required: bool = True) -> bool:
    """Check if env var exists and has value."""
    value = os.getenv(name)
    status = "✓" if value else "✗"
    req = "REQUIRED" if required else "optional"
    print(f"  {status} {name}: {req}")
    return bool(value)

def check_assembly_ai() -> bool:
    """Verify Assembly AI API key."""
    print("\n📍 Assembly AI (Speech-to-Text)")
    api_key = os.getenv("ASSEMBLY_AI_API_KEY")
    if not api_key:
        print("  ✗ ASSEMBLY_AI_API_KEY not set")
        return False
    print(f"  ✓ ASSEMBLY_AI_API_KEY: {api_key[:20]}...")
    return True

def check_google_tts() -> bool:
    """Verify Google Cloud TTS credentials."""
    print("\n📍 Google Cloud TTS (Text-to-Speech)")

    creds_b64 = os.getenv("GOOGLE_CLOUD_TTS_CREDENTIALS_JSON")
    project_id = os.getenv("GOOGLE_CLOUD_TTS_PROJECT_ID")

    if not creds_b64:
        print("  ✗ GOOGLE_CLOUD_TTS_CREDENTIALS_JSON not set")
        return False

    if not project_id:
        print("  ✗ GOOGLE_CLOUD_TTS_PROJECT_ID not set")
        return False

    try:
        creds_json = base64.b64decode(creds_b64).decode("utf-8")
        creds_dict = json.loads(creds_json)

        if "project_id" not in creds_dict:
            print("  ✗ Invalid credentials JSON (missing project_id)")
            return False

        print(f"  ✓ GOOGLE_CLOUD_TTS_CREDENTIALS_JSON: valid base64 JSON")
        print(f"  ✓ GOOGLE_CLOUD_TTS_PROJECT_ID: {project_id}")
        print(f"    - Service account: {creds_dict.get('client_email', '?')}")
        return True
    except Exception as e:
        print(f"  ✗ Failed to decode credentials: {e}")
        return False

def check_twilio() -> bool:
    """Verify Twilio config."""
    print("\n📍 Twilio (Phone Provider)")

    has_sid = check_env_var("TWILIO_ACCOUNT_SID")
    has_token = check_env_var("TWILIO_AUTH_TOKEN")
    has_phone = check_env_var("TWILIO_FROM_NUMBER", required=False)
    has_voice_host = check_env_var("VOICE_WEBHOOK_HOST", required=False)

    return has_sid and has_token

def check_openai() -> bool:
    """Verify OpenAI API key (for Claude decisions)."""
    print("\n📍 OpenAI API (Claude Decisions)")
    return check_env_var("OPENAI_API_KEY")

def check_tts_provider() -> bool:
    """Verify TTS provider is configured."""
    print("\n📍 TTS Provider Configuration")
    provider = os.getenv("TTS_PROVIDER", "google-cloud")
    print(f"  ✓ TTS_PROVIDER: {provider}")
    return True

def main():
    """Run all checks."""
    print("=" * 70)
    print("VOICE ORCHESTRATOR CONFIGURATION CHECK")
    print("=" * 70)

    results = {
        "Assembly AI": check_assembly_ai(),
        "Google Cloud TTS": check_google_tts(),
        "Twilio": check_twilio(),
        "OpenAI": check_openai(),
        "TTS Provider": check_tts_provider(),
    }

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    for name, result in results.items():
        status = "✓ OK" if result else "✗ FAILED"
        print(f"  {status}: {name}")

    all_passed = all(results.values())

    print("\n" + "=" * 70)
    if all_passed:
        print("✅ ALL CHECKS PASSED - Ready to implement WebSocket handler!")
        print("=" * 70)
        return 0
    else:
        print("❌ SOME CHECKS FAILED - See above for details")
        print("=" * 70)
        return 1

if __name__ == "__main__":
    sys.exit(main())
