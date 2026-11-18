"""
Zerodha KiteConnect Authentication and Session Manager.
Handles login URL generation, token exchange, and daily session caching.
"""
import json
from pathlib import Path
from datetime import datetime, date
from typing import Optional
from kiteconnect import KiteConnect
from config.settings import settings


SESSION_FILE = Path(__file__).resolve().parent.parent / ".kite_session.json"


class KiteAuthManager:
    def __init__(self):
        self.api_key = settings.kite_api_key
        self.api_secret = settings.kite_api_secret
        self.user_id = settings.kite_user_id
        self.kite: Optional[KiteConnect] = None

    def get_kite_client(self) -> KiteConnect:
        """
        Initializes and returns an authenticated KiteConnect instance.
        """
        if not self.api_key:
            raise ValueError("KITE_API_KEY is not configured in .env. Please update .env with your credentials.")

        self.kite = KiteConnect(api_key=self.api_key)

        # 1. Check if access token is directly in .env
        if settings.kite_access_token:
            self.kite.set_access_token(settings.kite_access_token)
            return self.kite

        # 2. Check cached daily session
        cached_token = self._load_cached_token()
        if cached_token:
            self.kite.set_access_token(cached_token)
            return self.kite

        return self.kite

    def get_login_url(self) -> str:
        """Returns the login URL for user authentication in a browser."""
        if not self.kite:
            self.kite = KiteConnect(api_key=self.api_key)
        return self.kite.login_url()

    def complete_login(self, request_token: str) -> str:
        """
        Exchanges request_token for an access_token and saves to daily cache.
        """
        if not self.api_secret:
            raise ValueError("KITE_API_SECRET is required to generate access token.")

        if not self.kite:
            self.kite = KiteConnect(api_key=self.api_key)

        data = self.kite.generate_session(request_token, api_secret=self.api_secret)
        access_token = data["access_token"]
        self.kite.set_access_token(access_token)

        self._save_cached_token(access_token)
        return access_token

    def _load_cached_token(self) -> Optional[str]:
        if not SESSION_FILE.exists():
            return None
        try:
            with open(SESSION_FILE, "r") as f:
                data = json.load(f)
            # Kite access tokens expire at market open next day. Check if cached today.
            today_str = date.today().isoformat()
            if data.get("date") == today_str and data.get("access_token"):
                return data["access_token"]
        except Exception:
            return None
        return None

    def _save_cached_token(self, token: str):
        payload = {
            "date": date.today().isoformat(),
            "timestamp": datetime.now().isoformat(),
            "access_token": token,
        }
        with open(SESSION_FILE, "w") as f:
            json.dump(payload, f, indent=2)
