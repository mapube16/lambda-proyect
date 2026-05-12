"""
test_softseguros.py — Phase 18: SOFTSEGUROS Deudores Sync.

Wave 1 Nyquist-compliant xfail scaffold. Tests cover SOFTSEG-01 through SOFTSEG-10
(2 stubs per requirement). All stubs are marked xfail(strict=False) so CI does not
block on unimplemented features — they flip to PASS as implementation lands.

NOTE: backend/softseguros/ package does NOT exist yet. This file MUST be importable
without it — use lazy imports inside fixtures, never at module level.
"""
import pytest
import pytest_asyncio
import database
from mongomock_motor import AsyncMongoMockClient


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def reset_db():
    """Fresh in-memory MongoDB per test — mirrors test_cobranza.py pattern."""
    mock_client = AsyncMongoMockClient()
    await database.init_db(client=mock_client)
    yield
    await database.get_db().users.drop()


@pytest_asyncio.fixture
async def async_client():
    # Lazy import — backend/softseguros/ may not exist at collection time.
    from main import app
    from httpx import AsyncClient, ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


# ── SOFTSEG-01: Token Auth (header `Token`, not Bearer) ───────────────────────

async def test_softseg_01_authenticate_post():
    """SoftSegurosAdapter.authenticate() POSTs to /api-token-auth/ and returns token."""
    import respx
    from httpx import Response
    from softseguros.adapter import SoftSegurosAdapter

    base = "https://app.softseguros.com"
    with respx.mock(base_url=base, assert_all_called=True) as mock:
        route = mock.post("/api-token-auth/").mock(
            return_value=Response(200, json={"token": "abc123"})
        )
        adapter = SoftSegurosAdapter("user1", "pwd1", base_url=base)
        try:
            token = await adapter.authenticate()
            assert token == "abc123"
            assert adapter.token == "abc123"
            # verify request body
            assert route.called
            posted = route.calls.last.request
            assert posted.method == "POST"
            import json as _json
            payload = _json.loads(posted.content.decode("utf-8"))
            assert payload == {"username": "user1", "password": "pwd1"}
        finally:
            await adapter.close()


async def test_softseg_01_header_uses_token_not_bearer():
    """Subsequent authenticated requests use header 'Authorization: Token <x>' (NOT Bearer)."""
    import respx
    from httpx import Response
    from softseguros.adapter import SoftSegurosAdapter

    base = "https://app.softseguros.com"
    with respx.mock(base_url=base, assert_all_called=False) as mock:
        mock.post("/api-token-auth/").mock(
            return_value=Response(200, json={"token": "tok-xyz"})
        )
        list_route = mock.get("/api/pagopoliza/").mock(
            return_value=Response(200, json={"results": [], "count": 0})
        )
        adapter = SoftSegurosAdapter("u", "p", base_url=base)
        try:
            await adapter.list_pagopoliza(page=1)
            assert list_route.called
            req = list_route.calls.last.request
            auth = req.headers.get("Authorization", "")
            assert auth == "Token tok-xyz"
            assert not auth.lower().startswith("bearer"), \
                f"Adapter must NOT use Bearer; got {auth!r}"
        finally:
            await adapter.close()


# ── SOFTSEG-02: Encrypted credentials per user ────────────────────────────────

async def test_softseg_02_save_credentials_encrypts(async_client):
    """save_credentials() Fernet-encrypts password and persists to softseguros_credentials."""
    from softseguros.credentials import save_credentials
    db = database.get_db()
    plaintext = "super-secret-password-123"
    await save_credentials(db, user_id="u1", username="corredor@example.com", password=plaintext)
    doc = await db.softseguros_credentials.find_one({"user_id": "u1"})
    assert doc is not None
    assert doc["username"] == "corredor@example.com"
    # ciphertext stored, NOT plaintext
    assert "password_encrypted" in doc
    assert doc["password_encrypted"] != plaintext
    assert plaintext not in doc["password_encrypted"]
    # Fernet ciphertext starts with "gAAAAA" (version byte base64-encoded)
    assert doc["password_encrypted"].startswith("gAAAAA")
    assert "configured_at" in doc and "updated_at" in doc


async def test_softseg_02_get_credentials_decrypts(async_client):
    """get_credentials() decrypts ciphertext and returns (username, plaintext_password); never logs plaintext."""
    from softseguros.credentials import save_credentials, get_credentials
    db = database.get_db()
    plaintext = "another-secret-xyz"
    await save_credentials(db, user_id="u2", username="ana@example.com", password=plaintext)
    result = await get_credentials(db, user_id="u2")
    assert result is not None
    username, decrypted = result
    assert username == "ana@example.com"
    assert decrypted == plaintext
    # Missing user returns None
    assert await get_credentials(db, user_id="nonexistent") is None


# ── SOFTSEG-03: Fetch + enrich pagopoliza with cliente ────────────────────────

@pytest.mark.xfail(strict=False, reason="SOFTSEG-03 not implemented yet")
async def test_softseg_03_list_pagopoliza_paginates(async_client):
    """adapter.list_pagopoliza(page=1) hits ?page=N and returns dict with 'results' array."""
    raise NotImplementedError(
        "SOFTSEG-03: list_pagopoliza must paginate with ?page=N (10/page fixed) and return results array"
    )


@pytest.mark.xfail(strict=False, reason="SOFTSEG-03 not implemented yet")
async def test_softseg_03_enrich_with_cliente(async_client):
    """Sync engine enriches each pagopoliza with cliente data via /api/poliza/{id} → /api/cliente/{id}."""
    raise NotImplementedError(
        "SOFTSEG-03: sync must enrich pagopoliza by following poliza → cliente"
    )


# ── SOFTSEG-04: Concurrency control + retry resilience ────────────────────────

@pytest.mark.xfail(strict=False, reason="SOFTSEG-04 not implemented yet")
async def test_softseg_04_semaphore_limits_concurrency(async_client):
    """Sync respects asyncio.Semaphore(5) — never more than 5 concurrent SOFTSEGUROS requests."""
    raise NotImplementedError(
        "SOFTSEG-04: sync must cap concurrency at 5 via asyncio.Semaphore"
    )


async def test_softseg_04_retry_on_429_with_backoff(monkeypatch):
    """Adapter retries on HTTP 429 with exponential backoff respecting Retry-After header."""
    import asyncio as _asyncio
    import respx
    from httpx import Response
    from softseguros.adapter import SoftSegurosAdapter

    # Speed up tenacity exponential waits and Retry-After sleeps
    async def _no_sleep(_seconds):
        return None
    monkeypatch.setattr(_asyncio, "sleep", _no_sleep)
    # Also patch tenacity's blocking sleep through nap
    import tenacity.nap as _nap
    monkeypatch.setattr(_nap, "sleep", lambda s: None)

    sleep_calls: list[float] = []
    real_sleep = _no_sleep

    async def _tracking_sleep(seconds):
        sleep_calls.append(seconds)
        return await real_sleep(seconds)
    monkeypatch.setattr("softseguros.adapter.asyncio.sleep", _tracking_sleep)

    base = "https://app.softseguros.com"
    with respx.mock(base_url=base, assert_all_called=False) as mock:
        mock.post("/api-token-auth/").mock(
            return_value=Response(200, json={"token": "t-1"})
        )
        responses = [
            Response(429, headers={"Retry-After": "1"}, json={"detail": "throttled"}),
            Response(429, headers={"Retry-After": "1"}, json={"detail": "throttled"}),
            Response(200, json={"results": [{"id": "p1"}], "count": 1}),
        ]
        call_count = {"n": 0}

        def _side_effect(request):
            i = call_count["n"]
            call_count["n"] += 1
            return responses[min(i, len(responses) - 1)]

        mock.get("/api/pagopoliza/").mock(side_effect=_side_effect)

        adapter = SoftSegurosAdapter("u", "p", base_url=base)
        try:
            result = await adapter.list_pagopoliza(page=1)
            assert result == {"results": [{"id": "p1"}], "count": 1}
            # Must have retried at least twice (3 total attempts)
            assert call_count["n"] == 3
            # Retry-After honored at least once
            assert any(s == 1.0 for s in sleep_calls), \
                f"Expected Retry-After=1s sleep; got {sleep_calls!r}"
        finally:
            await adapter.close()


# ── SOFTSEG-05: Classification ────────────────────────────────────────────────

@pytest.mark.xfail(strict=False, reason="SOFTSEG-05 not implemented yet")
async def test_softseg_05_classify_ya_vencidos(async_client):
    """classify_pagopoliza returns 'ya_vencidos' when fecha_pago < today AND comisionada=false."""
    raise NotImplementedError(
        "SOFTSEG-05: classify_pagopoliza must return 'ya_vencidos' for past-due unpaid cuotas"
    )


@pytest.mark.xfail(strict=False, reason="SOFTSEG-05 not implemented yet")
async def test_softseg_05_classify_proximos_a_vencer(async_client):
    """classify_pagopoliza returns 'proximos_a_vencer' when fecha_pago in [today, today+30] AND comisionada=false."""
    raise NotImplementedError(
        "SOFTSEG-05: classify_pagopoliza must return 'proximos_a_vencer' for cuotas in the next 30 days"
    )


# ── SOFTSEG-06: Three sync modes (onboarding, manual rate-limited) ────────────

@pytest.mark.xfail(strict=False, reason="SOFTSEG-06 not implemented yet")
async def test_softseg_06_configure_triggers_onboarding(async_client):
    """POST /api/debtors/configure-softseguros validates credentials and triggers onboarding sync in background."""
    raise NotImplementedError(
        "SOFTSEG-06: configure-softseguros must validate creds and kick off background onboarding sync"
    )


@pytest.mark.xfail(strict=False, reason="SOFTSEG-06 not implemented yet")
async def test_softseg_06_sync_now_rate_limit(async_client):
    """POST /api/debtors/sync-now returns 429 when last manual sync was < 5 minutes ago for that user."""
    raise NotImplementedError(
        "SOFTSEG-06: sync-now must enforce 5-min rate limit per user (429 response)"
    )


# ── SOFTSEG-07: Pre-call freshness check with fail-open ───────────────────────

@pytest.mark.xfail(strict=False, reason="SOFTSEG-07 not implemented yet")
async def test_softseg_07_verify_fresh_already_paid(async_client):
    """verify-fresh returns should_call=false + reason='already_paid' when comisionada=true; updates local status='pagado', is_active=false."""
    raise NotImplementedError(
        "SOFTSEG-07: verify-fresh must cancel call and mark pagado when SOFTSEGUROS comisionada=true"
    )


@pytest.mark.xfail(strict=False, reason="SOFTSEG-07 not implemented yet")
async def test_softseg_07_verify_fresh_fail_open(async_client):
    """verify-fresh returns should_call=true with warning when SOFTSEGUROS times out (fail-open)."""
    raise NotImplementedError(
        "SOFTSEG-07: verify-fresh must fail-open (should_call=true) on SOFTSEGUROS timeout/5xx"
    )


# ── SOFTSEG-08: Filtered REST API + multi-tenant ──────────────────────────────

@pytest.mark.xfail(strict=False, reason="SOFTSEG-08 not implemented yet")
async def test_softseg_08_list_filtered_by_status(async_client):
    """GET /api/debtors?status=ya_vencidos returns only docs where status_softseguros='ya_vencidos', is_active=true, scoped to current user_id."""
    raise NotImplementedError(
        "SOFTSEG-08: GET /api/debtors must filter by status_softseguros and current user_id"
    )


@pytest.mark.xfail(strict=False, reason="SOFTSEG-08 not implemented yet")
async def test_softseg_08_tenant_isolation(async_client):
    """GET /api/debtors/{id} returns 404 when the debtor belongs to a different user_id."""
    raise NotImplementedError(
        "SOFTSEG-08: GET /api/debtors/{id} must enforce tenant isolation (404 on cross-user access)"
    )


# ── SOFTSEG-09: Soft-delete + idempotency ─────────────────────────────────────

@pytest.mark.xfail(strict=False, reason="SOFTSEG-09 not implemented yet")
async def test_softseg_09_soft_delete_on_404(async_client):
    """When pagopoliza disappears from listing, sync verifies via single GET; on 404 marks local is_active=false, status_softseguros='eliminado' (never hard-delete)."""
    raise NotImplementedError(
        "SOFTSEG-09: missing pagopoliza must be soft-deleted (is_active=false, status='eliminado'), never hard-deleted"
    )


@pytest.mark.xfail(strict=False, reason="SOFTSEG-09 not implemented yet")
async def test_softseg_09_sync_is_idempotent(async_client):
    """Multiple syncs for the same pagopoliza_id are idempotent — unique index (user_id, softseguros_pagopoliza_id) prevents duplicates."""
    raise NotImplementedError(
        "SOFTSEG-09: sync must be idempotent — unique (user_id, softseguros_pagopoliza_id) index"
    )


# ── SOFTSEG-10: Sync status + onboarding state endpoints ──────────────────────

@pytest.mark.xfail(strict=False, reason="SOFTSEG-10 not implemented yet")
async def test_softseg_10_sync_status_endpoint(async_client):
    """GET /api/debtors/sync-status returns last_sync_at, last_sync_mode, debtors_created/updated counts from softseguros_sync_logs."""
    raise NotImplementedError(
        "SOFTSEG-10: GET /api/debtors/sync-status must report last sync metadata from sync_logs"
    )


@pytest.mark.xfail(strict=False, reason="SOFTSEG-10 not implemented yet")
async def test_softseg_10_configure_never_returns_password(async_client):
    """GET /api/debtors/configure-softseguros returns {configured: bool, configured_at: datetime|null}; never returns password field."""
    raise NotImplementedError(
        "SOFTSEG-10: GET configure-softseguros must NEVER return the password field"
    )
