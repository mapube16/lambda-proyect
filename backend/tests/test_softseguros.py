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

# NOTE: /api/pagopoliza/ returned 504 in the live smoke test — the real model is
# /api/poliza/, which already embeds all cliente_* fields (no separate cliente fetch).
async def test_softseg_03_list_polizas_paginates(async_client):
    """adapter.list_polizas(page=N) hits /api/poliza/?page=N and returns the paginated dict."""
    import respx
    from httpx import Response
    from softseguros.adapter import SoftSegurosAdapter

    base = "https://app.softseguros.com"
    with respx.mock(base_url=base, assert_all_called=False) as mock:
        mock.post("/api-token-auth/").mock(return_value=Response(200, json={"token": "t"}))

        def _side_effect(request):
            page = request.url.params.get("page", "1")
            if page == "1":
                return Response(200, json={
                    "count": 12, "next": "page=2", "previous": None,
                    "results": [{"id": i} for i in range(1, 11)],
                })
            return Response(200, json={
                "count": 12, "next": None, "previous": "page=1",
                "results": [{"id": 11}, {"id": 12}],
            })

        mock.get("/api/poliza/").mock(side_effect=_side_effect)

        adapter = SoftSegurosAdapter("u", "p", base_url=base)
        try:
            p1 = await adapter.list_polizas(page=1)
            assert isinstance(p1, dict)
            assert isinstance(p1["results"], list) and len(p1["results"]) == 10
            assert adapter.parse_next_page(p1["next"]) == 2
            p2 = await adapter.list_polizas(page=2)
            assert len(p2["results"]) == 2
            assert adapter.parse_next_page(p2["next"]) is None
        finally:
            await adapter.close()


async def test_softseg_03_enrich_with_cliente(async_client):
    """Each póliza already embeds cliente_* fields; run_sync maps them onto the debtor doc."""
    import respx
    from httpx import Response
    import database
    from softseguros.credentials import save_credentials
    from softseguros.sync import run_sync

    db = database.get_db()
    await save_credentials(db, user_id="u1", username="c@e.com", password="pw")

    poliza = {
        "id": 501, "numero_poliza": "POL-501", "cliente": 99,
        "cliente_numero_documento": "123456", "cliente_nombres": "Ana", "cliente_apellidos": "Pérez",
        "cliente_celular": "+573001112233", "cliente_email": "ana@cli.com",
        "aseguradora_nit": "900123", "ramo_nombre": "Autos", "ramo_global_nombre": "Vehículos",
        "vendedores_nombre": "Vendor X", "estado_poliza_nombre": "Vigente",
        "estado_cartera": "Pendiente por pagar", "prima": 100.0, "total": 120.0, "total_pagado": None,
        "recaudado": False, "fecha_inicio": "2026-01-01", "fecha_fin": "2020-01-01",
        "fecha_limite_pago": None, "periodicidad": "Anual", "comicionada": False,
    }
    base = "https://app.softseguros.com"
    with respx.mock(base_url=base, assert_all_called=False) as mock:
        mock.post("/api-token-auth/").mock(return_value=Response(200, json={"token": "t"}))
        mock.get("/api/poliza/").mock(return_value=Response(200, json={
            "count": 1, "next": None, "previous": None, "results": [poliza],
        }))
        await run_sync(db, "u1", mode="onboarding")

    doc = await db.debtors.find_one({"user_id": "u1", "softseguros_poliza_id": 501})
    assert doc is not None
    assert doc["nombre"] == "Ana Pérez"
    assert doc["telefono"] == "+573001112233"
    assert doc["cliente_email"] == "ana@cli.com"
    assert doc["cliente_documento"] == "123456"
    assert doc["numero_poliza"] == "POL-501"
    assert doc["softseguros_cliente_id"] == 99
    assert doc["status_softseguros"] == "ya_vencidos"
    assert doc["source"] == "softseguros"
    # Phase 17 invariants seeded.
    assert doc["estado"] == "pendiente" and doc["intentos"] == 0


# ── SOFTSEG-04: Concurrency control + retry resilience ────────────────────────

async def test_softseg_04_semaphore_limits_concurrency(async_client, monkeypatch):
    """run_sync never has more than 5 SOFTSEGUROS HTTP requests in flight at once."""
    import asyncio as _asyncio
    import respx
    from httpx import Response
    import database
    from softseguros.credentials import save_credentials
    from softseguros.sync import run_sync

    db = database.get_db()
    await save_credentials(db, user_id="u1", username="c@e.com", password="pw")

    # 30 pólizas / 10 per page = 3 pages. Make each /api/poliza/ response slow so
    # concurrent requests overlap, and record the high-water mark of in-flight calls.
    in_flight = {"now": 0, "max": 0}
    lock = _asyncio.Lock()

    async def _enter():
        async with lock:
            in_flight["now"] += 1
            in_flight["max"] = max(in_flight["max"], in_flight["now"])

    async def _exit():
        async with lock:
            in_flight["now"] -= 1

    base = "https://app.softseguros.com"
    with respx.mock(base_url=base, assert_all_called=False) as mock:
        mock.post("/api-token-auth/").mock(return_value=Response(200, json={"token": "t"}))

        # respx side_effect can be a coroutine function.
        async def _poliza_side_effect(request):
            await _enter()
            try:
                await _asyncio.sleep(0.02)
            finally:
                await _exit()
            page = int(request.url.params.get("page", "1"))
            results = [{
                "id": (page - 1) * 10 + i,
                "estado_cartera": "Pendiente por pagar",
                "fecha_fin": "2020-01-01", "fecha_limite_pago": None,
                "recaudado": False, "total": 50.0,
                "cliente_celular": f"+5731{(page - 1) * 10 + i:05d}",
                "cliente_nombres": "X", "cliente_apellidos": "Y",
            } for i in range(1, 11)]
            return Response(200, json={
                "count": 30,
                "next": ("page=%d" % (page + 1)) if page < 3 else None,
                "previous": None, "results": results,
            })

        mock.get("/api/poliza/").mock(side_effect=_poliza_side_effect)
        await run_sync(db, "u1", mode="onboarding")

    assert in_flight["max"] <= 5, f"concurrency exceeded 5: peak={in_flight['max']}"
    assert in_flight["max"] >= 1
    # All 30 pólizas persisted.
    assert await db.debtors.count_documents({"user_id": "u1", "source": "softseguros"}) == 30


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

async def test_softseg_05_classify_ya_vencidos():
    """classify_pagopoliza returns 'ya_vencidos' when fecha_pago < today AND comisionada=false."""
    from datetime import date, timedelta
    from softseguros.classifier import classify_pagopoliza

    today = date(2026, 5, 12)
    # Past-due unpaid → ya_vencidos
    assert classify_pagopoliza(today - timedelta(days=1), False, today) == "ya_vencidos"
    assert classify_pagopoliza(today - timedelta(days=90), False, today) == "ya_vencidos"
    # Past-due but comisionada=true → pagado wins
    assert classify_pagopoliza(today - timedelta(days=1), True, today) == "pagado"


async def test_softseg_05_classify_proximos_a_vencer():
    """classify_pagopoliza returns 'proximos_a_vencer' when fecha_pago in [today, today+30] AND comisionada=false."""
    from datetime import date, timedelta
    from softseguros.classifier import classify_pagopoliza

    today = date(2026, 5, 12)
    # In window
    assert classify_pagopoliza(today, False, today) == "proximos_a_vencer"
    assert classify_pagopoliza(today + timedelta(days=15), False, today) == "proximos_a_vencer"
    assert classify_pagopoliza(today + timedelta(days=30), False, today) == "proximos_a_vencer"
    # Beyond window → futuro
    assert classify_pagopoliza(today + timedelta(days=31), False, today) == "futuro"
    # In-window but comisionada=true → pagado
    assert classify_pagopoliza(today + timedelta(days=5), True, today) == "pagado"


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

def _vencido_poliza(pid: int, **over) -> dict:
    base = {
        "id": pid, "numero_poliza": f"POL-{pid}", "cliente": pid * 10,
        "cliente_numero_documento": str(pid), "cliente_nombres": "N", "cliente_apellidos": "A",
        "cliente_celular": f"+5730000{pid:04d}", "cliente_email": "n@a.com", "aseguradora_nit": "900",
        "ramo_nombre": "R", "ramo_global_nombre": "RG", "vendedores_nombre": "V",
        "estado_poliza_nombre": "Vigente", "estado_cartera": "Pendiente por pagar",
        "prima": 10.0, "total": 50.0, "total_pagado": None, "recaudado": False,
        "fecha_inicio": "2026-01-01", "fecha_fin": "2020-01-01", "fecha_limite_pago": None,
        "periodicidad": "Anual", "comicionada": False,
    }
    base.update(over)
    return base


async def test_softseg_09_soft_delete_on_404(async_client):
    """A cron_daily sync: a póliza now returning 404 (or 'Pagada') soft-deletes the local debtor — never hard-delete."""
    import respx
    from httpx import Response
    import database
    from softseguros.credentials import save_credentials
    from softseguros.sync import run_sync

    db = database.get_db()
    await save_credentials(db, user_id="u1", username="c@e.com", password="pw")

    base = "https://app.softseguros.com"
    # First (onboarding) sync: two pólizas 301 & 302 → two active debtors.
    with respx.mock(base_url=base, assert_all_called=False) as mock:
        mock.post("/api-token-auth/").mock(return_value=Response(200, json={"token": "t"}))
        mock.get("/api/poliza/").mock(return_value=Response(200, json={
            "count": 2, "next": None, "previous": None,
            "results": [_vencido_poliza(301), _vencido_poliza(302)],
        }))
        await run_sync(db, "u1", mode="onboarding")
    assert await db.debtors.count_documents({"user_id": "u1", "is_active": True}) == 2

    # Second (cron_daily) sync: listing now only returns 301; 302 → 404 on GET /api/poliza/302.
    with respx.mock(base_url=base, assert_all_called=False) as mock:
        mock.post("/api-token-auth/").mock(return_value=Response(200, json={"token": "t"}))
        mock.get("/api/poliza/", params={"page": "1"}).mock(return_value=Response(200, json={
            "count": 2, "next": None, "previous": None, "results": [_vencido_poliza(301)],
        }))
        mock.get("/api/poliza/302").mock(return_value=Response(404, json={"detail": "not found"}))
        await run_sync(db, "u1", mode="cron_daily")

    doc302 = await db.debtors.find_one({"user_id": "u1", "softseguros_poliza_id": 302})
    assert doc302 is not None, "soft-delete must NOT hard-delete the document"
    assert doc302["is_active"] is False
    assert doc302["status_softseguros"] == "eliminado"
    doc301 = await db.debtors.find_one({"user_id": "u1", "softseguros_poliza_id": 301})
    assert doc301["is_active"] is True


async def test_softseg_09_sync_is_idempotent(async_client):
    """Running run_sync twice over the same data yields exactly one debtor doc per poliza_id."""
    import respx
    from httpx import Response
    import database
    from softseguros.credentials import save_credentials
    from softseguros.sync import run_sync

    db = database.get_db()
    await save_credentials(db, user_id="u1", username="c@e.com", password="pw")

    base = "https://app.softseguros.com"
    polizas = [_vencido_poliza(401), _vencido_poliza(402)]

    def _run_once():
        return {"count": 2, "next": None, "previous": None, "results": polizas}

    for _ in range(2):
        with respx.mock(base_url=base, assert_all_called=False) as mock:
            mock.post("/api-token-auth/").mock(return_value=Response(200, json={"token": "t"}))
            mock.get("/api/poliza/").mock(return_value=Response(200, json=_run_once()))
            await run_sync(db, "u1", mode="onboarding")

    assert await db.debtors.count_documents({"user_id": "u1", "softseguros_poliza_id": 401}) == 1
    assert await db.debtors.count_documents({"user_id": "u1", "softseguros_poliza_id": 402}) == 1
    assert await db.debtors.count_documents({"user_id": "u1", "source": "softseguros"}) == 2


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
