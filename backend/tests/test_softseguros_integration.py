"""
test_softseguros_integration.py — Phase 18, Plan 05.

End-to-end integration test of the SOFTSEGUROS sync feature with the upstream
SOFTSEGUROS API fully mocked via respx (no real network calls):

  1. POST /api/debtors/configure-softseguros  → validates creds, runs onboarding sync
  2. Onboarding scans /api/poliza/ (3 pages, mixed estado_cartera / fecha_fin)
  3. GET /api/debtors?status=proximos_a_vencer  → only the soon-to-expire pólizas
  4. GET /api/debtors?status=ya_vencidos        → only the past-due pólizas
  5. POST /api/debtors/sync-now twice quickly   → second is 429 + Retry-After
  6. GET /api/debtors/{id}/verify-fresh on a now-"Pagada" póliza → should_call=false,
     reason='already_paid'; the debtor doc becomes is_active=false / status='pagado'
  7. Tenant isolation: a second JWT user sees none of the first user's debtors and
     gets 404 on the first user's debtor id.
"""
import re
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
import database
from mongomock_motor import AsyncMongoMockClient


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def reset_db():
    mock_client = AsyncMongoMockClient()
    await database.init_db(client=mock_client)
    yield
    await database.get_db().users.drop()


@pytest_asyncio.fixture
async def async_client():
    from main import app
    from httpx import AsyncClient, ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def _register_and_login(client, email, password="testpass123", enable_softseguros=True):
    resp = await client.post("/auth/register", json={"email": email, "password": password})
    assert resp.status_code in (200, 201), f"Register failed: {resp.text}"
    user = await database.get_user_by_email(email)
    assert user is not None
    if enable_softseguros:
        # No service is enabled by default — Landa staff authorizes it. The /api/debtors/*
        # endpoints are gated by company_voice.softseguros_enabled.
        await database.get_db().company_voice.update_one(
            {"user_id": str(user["id"])},
            {"$set": {"softseguros_enabled": True}, "$setOnInsert": {"user_id": str(user["id"])}},
            upsert=True,
        )
    from auth import create_access_token
    token = create_access_token(data={"sub": str(user["id"]), "role": user.get("role", "client")})
    return {"Authorization": f"Bearer {token}"}, str(user["id"])


# ── Mock póliza data ──────────────────────────────────────────────────────────

_TODAY = date.today()
_PAST = (_TODAY - timedelta(days=30)).isoformat()
_SOON = (_TODAY + timedelta(days=10)).isoformat()
_FAR = (_TODAY + timedelta(days=400)).isoformat()


def _poliza(pid, *, estado_cartera, fecha_fin, estado_poliza="Vigente", recaudado=False, total=100000.0):
    return {
        "id": pid, "numero_poliza": f"POL-{pid}", "cliente": pid * 10,
        "cliente_numero_documento": str(1000 + pid),
        "cliente_nombres": f"Nombre{pid}", "cliente_apellidos": f"Apellido{pid}",
        "cliente_celular": f"+5730000{pid:05d}", "cliente_email": f"cli{pid}@example.com",
        "aseguradora_nit": "900123456", "ramo_nombre": "Autos", "ramo_global_nombre": "Vehículos",
        "vendedores_nombre": "Vendedor X", "estado_poliza_nombre": estado_poliza,
        "estado_cartera": estado_cartera, "prima": total * 0.8, "total": total, "total_pagado": None,
        "recaudado": recaudado, "fecha_inicio": "2026-01-01", "fecha_fin": fecha_fin,
        "fecha_limite_pago": None, "periodicidad": "Anual", "comicionada": False,
    }


def _build_25_polizas():
    """25 pólizas: 8 past-due unpaid (ya_vencidos), 7 soon-unpaid (proximos), 10 paid/far (skipped)."""
    out = []
    pid = 1
    for _ in range(8):
        out.append(_poliza(pid, estado_cartera="Pendiente por pagar", fecha_fin=_PAST)); pid += 1
    for _ in range(7):
        out.append(_poliza(pid, estado_cartera="Sin pagos Asignados", fecha_fin=_SOON)); pid += 1
    for _ in range(5):
        out.append(_poliza(pid, estado_cartera="Pagada", fecha_fin=_PAST, recaudado=True)); pid += 1
    for _ in range(5):
        out.append(_poliza(pid, estado_cartera="Sin pagos Asignados", fecha_fin=_FAR)); pid += 1
    assert len(out) == 25
    return out


def _paginate(polizas, page_size=10):
    pages = {}
    n = len(polizas)
    npages = (n + page_size - 1) // page_size
    for i in range(npages):
        pg = i + 1
        chunk = polizas[i * page_size:(i + 1) * page_size]
        pages[pg] = {
            "count": n,
            "next": f"https://app.softseguros.com/api/poliza/?page={pg + 1}" if pg < npages else None,
            "previous": f"https://app.softseguros.com/api/poliza/?page={pg - 1}" if pg > 1 else None,
            "results": chunk,
        }
    return pages


# ── The test ──────────────────────────────────────────────────────────────────

async def test_softseguros_end_to_end(async_client):
    import respx
    from httpx import Response

    headers, user_id = await _register_and_login(async_client, "ss_e2e@example.com")
    base = "https://app.softseguros.com"

    polizas = _build_25_polizas()
    pages = _paginate(polizas)

    def _list_side_effect(request):
        pg = int(request.url.params.get("page", "1"))
        return Response(200, json=pages.get(pg, {"count": len(polizas), "next": None, "previous": None, "results": []}))

    # ── Step 1+2: configure → onboarding sync (BackgroundTask runs within this block) ──
    with respx.mock(base_url=base, assert_all_called=False) as mock:
        mock.post("/api-token-auth/").mock(return_value=Response(200, json={
            "id": 1908, "nombre_completo": "Cartera DPG", "perfil": 1,
            "perfil_name": "Cartera", "token": "tok-e2e", "nombre_marca": "DPG", "username": "cartera.dpg",
        }))
        mock.get("/api/poliza/").mock(side_effect=_list_side_effect)
        resp = await async_client.post(
            "/api/debtors/configure-softseguros",
            json={"username": "cartera.dpg", "password": "secret"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["sync_started"] is True

    db = database.get_db()
    # credentials persisted, no plaintext password
    cred = await db.softseguros_credentials.find_one({"user_id": user_id})
    assert cred is not None and "password" not in cred and cred["password_encrypted"].startswith("gAAAAA")
    # onboarding sync log written
    log = await db.softseguros_sync_logs.find_one({"user_id": user_id, "mode": "onboarding"})
    assert log is not None and log["status"] == "success"
    # 15 cobrable debtors persisted (8 vencidos + 7 proximos); the 10 paid/far skipped
    assert await db.debtors.count_documents({"user_id": user_id, "source": "softseguros", "is_active": True}) == 15

    # ── Step 3: list proximos_a_vencer ──
    r = await async_client.get("/api/debtors?status=proximos_a_vencer", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 7
    assert {it["status_softseguros"] for it in body["items"]} == {"proximos_a_vencer"}
    # client fields surfaced on the debtor doc
    sample = body["items"][0]
    assert sample["numero_poliza"].startswith("POL-")
    assert sample["cliente_email"].endswith("@example.com")
    assert sample["source"] == "softseguros"

    # ── Step 4: list ya_vencidos ──
    r = await async_client.get("/api/debtors?status=ya_vencidos", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 8
    assert {it["status_softseguros"] for it in body["items"]} == {"ya_vencidos"}

    # ── Step 5: sync-now twice quickly → second 429 ──
    with respx.mock(base_url=base, assert_all_called=False) as mock:
        mock.post("/api-token-auth/").mock(return_value=Response(200, json={"token": "tok-e2e"}))
        mock.get("/api/poliza/").mock(side_effect=_list_side_effect)
        r1 = await async_client.post("/api/debtors/sync-now", headers=headers)
        assert r1.status_code == 200, r1.text
        r2 = await async_client.post("/api/debtors/sync-now", headers=headers)
    assert r2.status_code == 429
    assert "Retry-After" in r2.headers
    assert int(r2.headers["Retry-After"]) > 0

    # ── Step 6: verify-fresh on a poliza that is now 'Pagada' ──
    # Pick one of the ya_vencidos debtors.
    target = await db.debtors.find_one({"user_id": user_id, "status_softseguros": "ya_vencidos"})
    assert target is not None
    target_id = str(target["_id"])
    target_poliza_id = target["softseguros_poliza_id"]
    with respx.mock(base_url=base, assert_all_called=False) as mock:
        mock.post("/api-token-auth/").mock(return_value=Response(200, json={"token": "tok-e2e"}))
        mock.get(f"/api/poliza/{target_poliza_id}").mock(return_value=Response(200, json=_poliza(
            target_poliza_id, estado_cartera="Pagada", fecha_fin=_PAST, recaudado=True,
        )))
        vr = await async_client.get(f"/api/debtors/{target_id}/verify-fresh", headers=headers)
    assert vr.status_code == 200, vr.text
    vbody = vr.json()
    assert vbody["should_call"] is False
    assert vbody["reason"] == "already_paid"
    refreshed = await db.debtors.find_one({"_id": target["_id"]})
    assert refreshed["is_active"] is False
    assert refreshed["status_softseguros"] == "pagado"

    # ── Step 7: tenant isolation ──
    headers_b, user_id_b = await _register_and_login(async_client, "ss_e2e_b@example.com")
    # B lists debtors → empty
    rb = await async_client.get("/api/debtors", headers=headers_b)
    assert rb.status_code == 200
    assert rb.json()["items"] == []
    assert rb.json()["total"] == 0
    # B cannot fetch A's debtor
    rb2 = await async_client.get(f"/api/debtors/{target_id}", headers=headers_b)
    assert rb2.status_code == 404
    # B cannot verify-fresh A's debtor
    rb3 = await async_client.get(f"/api/debtors/{target_id}/verify-fresh", headers=headers_b)
    assert rb3.status_code == 404


async def test_softseguros_configure_bad_credentials(async_client):
    """Bad SOFTSEGUROS creds → 400; nothing persisted."""
    import respx
    from httpx import Response

    headers, user_id = await _register_and_login(async_client, "ss_badcreds@example.com")
    base = "https://app.softseguros.com"
    with respx.mock(base_url=base, assert_all_called=False) as mock:
        mock.post("/api-token-auth/").mock(return_value=Response(401, json={"detail": "Invalid credentials"}))
        resp = await async_client.post(
            "/api/debtors/configure-softseguros",
            json={"username": "wrong", "password": "wrong"},
            headers=headers,
        )
    assert resp.status_code == 400
    db = database.get_db()
    assert await db.softseguros_credentials.find_one({"user_id": user_id}) is None
