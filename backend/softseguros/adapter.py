"""
softseguros/adapter.py — Async HTTP adapter to the SOFTSEGUROS API.

- Auth: POST /api-token-auth/  →  {token}
- Header: Authorization: Token <x>   (Django REST Framework style, NOT Bearer)
- Pagination: ?page=N&order_by=<field>&sort_by=asc|desc  (fixed 10/page)
- Retry: tenacity exponential backoff on 429 and timeouts; honors Retry-After header
- 401: transparent single re-auth + retry of the same request
"""
import asyncio
import logging
from typing import Any, Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


# ── Exceptions ────────────────────────────────────────────────────────────────

class SoftSegurosAPIError(Exception):
    """Base error for SOFTSEGUROS API failures."""


class SoftSegurosAuthError(SoftSegurosAPIError):
    """Raised when authentication fails or 401 persists after re-auth."""


class SoftSegurosNotFoundError(SoftSegurosAPIError):
    """Raised on 404 — resource no longer exists upstream (drives soft-delete)."""


class SoftSegurosRateLimitError(SoftSegurosAPIError):
    """Raised on 429 — retryable by tenacity."""


class SoftSegurosServerError(SoftSegurosAPIError):
    """Raised on 5xx — retryable by tenacity."""


# ── Adapter ───────────────────────────────────────────────────────────────────

class SoftSegurosAdapter:
    """
    Per-user SOFTSEGUROS API adapter. Constructor takes explicit credentials and base URL
    (no env reads inside) so it is trivially testable and multi-tenant safe.
    """

    def __init__(
        self,
        username: str,
        password: str,
        base_url: str = "https://app.softseguros.com",
        timeout: float = 30.0,
    ):
        self.username = username
        self._password = password
        self.base_url = base_url.rstrip("/")
        self.token: Optional[str] = None
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            limits=httpx.Limits(max_connections=10),
        )

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def close(self) -> None:
        """Close the underlying httpx.AsyncClient."""
        await self._client.aclose()

    async def __aenter__(self) -> "SoftSegurosAdapter":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    # ── Auth ─────────────────────────────────────────────────────────────────

    async def authenticate(self) -> str:
        """POST /api-token-auth/ → store and return token. Raises SoftSegurosAuthError on failure."""
        try:
            response = await self._client.post(
                "/api-token-auth/",
                json={"username": self.username, "password": self._password},
            )
        except httpx.HTTPError as exc:
            raise SoftSegurosAuthError(f"auth network error: {exc!r}") from exc

        if response.status_code != 200:
            # Never log password
            logger.error(
                "softseguros auth failed status=%s username=%r",
                response.status_code, self.username,
            )
            raise SoftSegurosAuthError(
                f"authenticate failed: status={response.status_code}"
            )

        try:
            data = response.json()
            self.token = data["token"]
        except (ValueError, KeyError) as exc:
            raise SoftSegurosAuthError(f"auth response malformed: {exc!r}") from exc

        return self.token

    def _auth_headers(self) -> dict:
        if not self.token:
            return {}
        # Django REST Framework convention — NOT "Bearer".
        return {"Authorization": f"Token {self.token}"}

    # ── Core request with retry + 401 re-auth ────────────────────────────────

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(
            (httpx.TimeoutException, SoftSegurosRateLimitError, SoftSegurosServerError)
        ),
        reraise=True,
    )
    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """
        Make an authenticated request. Retries on 429/5xx/timeouts with exponential backoff.
        On 401, performs one transparent re-auth and retries the same call once.
        """
        # Ensure we have a token; do not retry this on auth failure
        if not self.token:
            await self.authenticate()

        headers = kwargs.pop("headers", {}) or {}
        headers.update(self._auth_headers())

        response = await self._client.request(method, path, headers=headers, **kwargs)

        # ── 401: single transparent re-auth ──────────────────────────────────
        if response.status_code == 401:
            logger.info("softseguros got 401, re-authenticating once and retrying %s %s", method, path)
            self.token = None
            await self.authenticate()
            headers.update(self._auth_headers())
            response = await self._client.request(method, path, headers=headers, **kwargs)
            if response.status_code == 401:
                raise SoftSegurosAuthError(f"401 persists after re-auth on {method} {path}")

        # ── 429: respect Retry-After, then raise retryable ───────────────────
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            wait_seconds = 0.0
            if retry_after:
                try:
                    wait_seconds = float(retry_after)
                except ValueError:
                    wait_seconds = 0.0
            if wait_seconds > 0:
                logger.info("softseguros 429 — sleeping %.2fs before retry", wait_seconds)
                await asyncio.sleep(wait_seconds)
            raise SoftSegurosRateLimitError(
                f"429 from {method} {path} (Retry-After={retry_after})"
            )

        # ── 5xx: raise retryable ─────────────────────────────────────────────
        if 500 <= response.status_code < 600:
            raise SoftSegurosServerError(
                f"{response.status_code} from {method} {path}"
            )

        # ── 404: distinct non-retryable (drives soft-delete) ─────────────────
        if response.status_code == 404:
            raise SoftSegurosNotFoundError(f"404 from {method} {path}")

        # ── 4xx other than 401/404/429: non-retryable ────────────────────────
        if 400 <= response.status_code < 500:
            raise SoftSegurosAPIError(
                f"{response.status_code} from {method} {path}: {response.text[:200]}"
            )

        return response

    async def _get_json(self, path: str, params: Optional[dict] = None) -> Any:
        response = await self._request("GET", path, params=params)
        return response.json()

    # ── Endpoints ────────────────────────────────────────────────────────────

    async def list_pagopoliza(self, page: int = 1) -> dict:
        """GET /api/pagopoliza/?page=N&order_by=fecha_pago&sort_by=asc — paginated cuotas list."""
        return await self._get_json(
            "/api/pagopoliza/",
            params={"page": page, "order_by": "fecha_pago", "sort_by": "asc"},
        )

    async def get_pagopoliza(self, pagopoliza_id: str) -> dict:
        """GET /api/pagopoliza/{id} — single cuota detail."""
        return await self._get_json(f"/api/pagopoliza/{pagopoliza_id}")

    async def get_pagopoliza_safe(self, pagopoliza_id: str) -> Optional[dict]:  # pragma: no cover
        """Legacy helper (unused — /api/pagopoliza/ is broken on SOFTSEGUROS, returns 504)."""
        return await self._get_json(f"/api/pagopoliza/{pagopoliza_id}")

    # ── Póliza endpoints (the real model — /api/pagopoliza/ is broken upstream) ──

    async def list_polizas(self, page: int = 1) -> dict:
        """
        GET /api/poliza/?page=N — paginated list of pólizas (10/page, FIXED).

        Server-side filters / page_size / ordering are all ignored — only ?page=N works.
        Returns the raw response dict: {"count": int, "next": "page=N"|None, "previous": ..., "results": [...]}.
        """
        return await self._get_json("/api/poliza/", params={"page": page})

    async def get_poliza(self, poliza_id) -> dict:
        """GET /api/poliza/{id} — single póliza dict (raises SoftSegurosAPIError on 404)."""
        return await self._get_json(f"/api/poliza/{poliza_id}")

    @staticmethod
    def parse_next_page(next_token: Optional[str]) -> Optional[int]:
        """
        SOFTSEGUROS returns `next` as a bare token like "page=2" (not a full URL).
        Parse the page number out of it. Returns None when there is no next page.
        """
        if not next_token:
            return None
        s = str(next_token)
        # Handle "page=2", "?page=2", or even a full "...&page=2" just in case.
        marker = "page="
        idx = s.rfind(marker)
        if idx == -1:
            return None
        tail = s[idx + len(marker):]
        digits = ""
        for ch in tail:
            if ch.isdigit():
                digits += ch
            else:
                break
        return int(digits) if digits else None
