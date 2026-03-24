"""
google_auth.py — One-time OAuth2 flow to get Google Calendar refresh token.

Run once:
    cd backend
    python google_auth.py

Opens browser for Google login → paste the code → prints refresh token.
Add GOOGLE_REFRESH_TOKEN=<token> to your .env file.
"""
import os
import json
from pathlib import Path

CLIENT_ID = os.getenv(
    "GOOGLE_CLIENT_ID",
    "857510443123-m0v5596ud47t5f536i1kdhobnr3fgslb.apps.googleusercontent.com",
)
CLIENT_SECRET = os.getenv(
    "GOOGLE_CLIENT_SECRET",
    "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",
)

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]

def main():
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Installing google-auth-oauthlib...")
        os.system("pip install google-auth-oauthlib google-api-python-client")
        from google_auth_oauthlib.flow import InstalledAppFlow

    client_config = {
        "installed": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0)

    print("\n✅ Autorización exitosa!\n")
    print("Agrega esto a tu .env:")
    print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}\n")

    # Also save to a local file as backup
    token_path = Path(__file__).parent / "google_token.json"
    token_path.write_text(json.dumps({
        "refresh_token": creds.refresh_token,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }))
    print(f"También guardado en: {token_path}")


if __name__ == "__main__":
    main()
