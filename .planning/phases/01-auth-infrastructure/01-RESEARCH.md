# Phase 1: Auth Infrastructure - Research

**Researched:** 2026-03-17
**Domain:** FastAPI JWT authentication, aiosqlite user persistence, WebSocket auth
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| AUTH-01 | Usuario puede registrarse con email y password | Password hashing with passlib/bcrypt, aiosqlite users table, POST /auth/register returning 201 with no raw password in response |
| AUTH-02 | Usuario puede hacer login con email y password y recibir JWT | python-jose JWT creation, OAuth2PasswordBearer flow, POST /auth/login returning signed token |
| AUTH-03 | El JWT protege todos los endpoints REST y el WebSocket connection | get_current_user dependency injected into every route, WebSocket token via query param + WebSocketException on failure |
</phase_requirements>

---

## Summary

This phase adds JWT authentication to a brownfield FastAPI 0.109.x / 0.115.x application that currently has zero auth. The existing `main.py` has flat REST endpoints, a global `ConnectionManager` that broadcasts to all WebSockets without any user keying, and an `orchestrator.py` that will be replaced in Phase 2. The auth layer must be bolted on without breaking any existing endpoint signatures — routes stay intact, a dependency is added to each.

The standard Python/FastAPI auth stack is `python-jose[cryptography]` for JWT signing/verification, `passlib[bcrypt]` for password hashing, and `aiosqlite` for async SQLite persistence of the users table. This is slightly older than FastAPI's latest official docs (which now prefer `PyJWT` + `pwdlib[argon2]`), but the project context explicitly locks `python-jose + passlib[bcrypt]` and both libraries are stable, widely deployed, and fully sufficient for MVP.

WebSocket auth is the only non-trivial part of this phase. The standard `Authorization: Bearer` header approach does not work for WebSocket handshakes in browser clients (the browser's `WebSocket` constructor does not allow setting custom headers). The documented pattern is to pass the JWT as a query parameter (`/ws?token=<jwt>`) and validate it inside the endpoint handler before accepting the connection — using `WebSocketException(code=WS_1008_POLICY_VIOLATION)` to close with 401-equivalent semantics.

**Primary recommendation:** Create `backend/auth.py` (password + JWT helpers), `backend/database.py` (aiosqlite pool init and users CRUD), and wire a `get_current_user` dependency into all existing routes and the `/ws` endpoint. Do not restructure `main.py` — add the dependency to each existing decorator.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| python-jose[cryptography] | 3.3.x | JWT sign/verify (HS256) | Project-locked; stable; widely deployed with FastAPI |
| passlib[bcrypt] | 1.7.x | Password hashing and verification | Project-locked; bcrypt is the appropriate cost factor for auth at MVP scale |
| aiosqlite | 0.20.x | Async SQLite driver for user persistence | Project-locked; zero infra; integrates directly with asyncio |
| fastapi.security.OAuth2PasswordBearer | (bundled with FastAPI) | Extracts Bearer token from Authorization header for REST | FastAPI built-in; generates OpenAPI security docs automatically |
| fastapi.security.HTTPBearer | (bundled with FastAPI) | Alternative extraction for explicit 401 control | Needed when OAuth2PasswordBearer returns 403 instead of 401 |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-dotenv | 1.0.x | Load SECRET_KEY, ALGORITHM, EXPIRE_MINUTES from .env | Already installed; use for all config |
| pydantic | 2.5.x | UserCreate, UserLogin, Token, TokenData request/response models | Already installed; define all auth schemas here |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| python-jose + passlib | PyJWT + pwdlib[argon2] | FastAPI official docs now recommend PyJWT + pwdlib; argon2 is more modern than bcrypt; BUT project context explicitly locks python-jose + passlib — do not switch |
| Direct aiosqlite queries | SQLAlchemy async ORM | ORM adds migration tooling but REQUIREMENTS.md explicitly prohibits SQLAlchemy and Alembic for MVP |
| JWT in-house | Auth0 / Clerk / Supabase Auth | REQUIREMENTS.md explicitly prohibits vendor auth for MVP |

**Installation:**
```bash
pip install "python-jose[cryptography]" "passlib[bcrypt]" aiosqlite python-dotenv
```

---

## Architecture Patterns

### Recommended Project Structure
```
backend/
├── main.py          # Existing — add Depends(get_current_user) to each route, do not restructure
├── models.py        # Existing — add UserInDB, UserPublic Pydantic models here
├── orchestrator.py  # Existing — do not touch (replaced in Phase 2)
├── auth.py          # NEW — CryptContext, create_access_token, get_current_user dependency
├── database.py      # NEW — aiosqlite init, users table DDL, get_user_by_email, create_user
└── requirements.txt # Update with new deps
```

### Pattern 1: Password Hashing Module (auth.py)
**What:** Centralize all crypto operations in one file so `main.py` stays clean.
**When to use:** Always — never call bcrypt or jose directly from route handlers.
**Example:**
```python
# Source: https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/
# Adapted for python-jose + passlib (project-locked stack)
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

SECRET_KEY = os.getenv("SECRET_KEY")  # from .env — never hardcode
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    return {"user_id": user_id}
```

### Pattern 2: aiosqlite Users Table (database.py)
**What:** Async SQLite init, users DDL, and CRUD helpers with raw queries (no ORM).
**When to use:** Database module is the only place that touches `aiosqlite` directly.
**Example:**
```python
# Source: aiosqlite 0.20.x official docs + project constraint (no SQLAlchemy)
import aiosqlite
from typing import Optional

DATABASE_URL = "hive_office.db"

async def init_db():
    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                hashed_password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

async def get_user_by_email(email: str) -> Optional[dict]:
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE email = ?", (email,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def create_user(email: str, hashed_password: str) -> dict:
    async with aiosqlite.connect(DATABASE_URL) as db:
        cursor = await db.execute(
            "INSERT INTO users (email, hashed_password) VALUES (?, ?)",
            (email, hashed_password)
        )
        await db.commit()
        return {"id": cursor.lastrowid, "email": email}
```

### Pattern 3: REST Route Protection
**What:** Add `Depends(get_current_user)` to each existing route without restructuring main.py.
**When to use:** Every route except `/`, `/auth/register`, `/auth/login`.
**Example:**
```python
# Source: https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/
from auth import get_current_user

# Before (existing):
@app.get("/api/agents")
async def get_agents():
    return orchestrator.get_all_agents()

# After (protected):
@app.get("/api/agents")
async def get_agents(current_user: dict = Depends(get_current_user)):
    return orchestrator.get_all_agents()
```

### Pattern 4: WebSocket Auth via Query Parameter
**What:** Browser WebSocket API does not allow setting Authorization headers. Pass JWT as `?token=` query param instead. Validate BEFORE calling `websocket.accept()`.
**When to use:** The `/ws` endpoint — the only WebSocket in this project.
**Example:**
```python
# Source: https://fastapi.tiangolo.com/advanced/websockets/
# + https://dev.to/hamurda/how-i-solved-websocket-authentication-in-fastapi-and-why-depends-wasnt-enough-1b68
from fastapi import WebSocket, WebSocketException, status, Query
from jose import JWTError, jwt

@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...)
):
    # Validate BEFORE accept — close before handshake completes if invalid
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    except JWTError:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    await manager.connect(websocket)
    # ... rest of handler unchanged
```

### Pattern 5: Auth Endpoints
**What:** POST /auth/register and POST /auth/login endpoints.
**Example:**
```python
from pydantic import BaseModel, EmailStr

class UserCreate(BaseModel):
    email: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

@app.post("/auth/register", status_code=201)
async def register(user: UserCreate):
    existing = await get_user_by_email(user.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed = hash_password(user.password)
    created = await create_user(user.email, hashed)
    return {"id": created["id"], "email": created["email"]}  # never return hash

@app.post("/auth/login", response_model=Token)
async def login(user: UserCreate):
    db_user = await get_user_by_email(user.email)
    if not db_user or not verify_password(user.password, db_user["hashed_password"]):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(data={"sub": str(db_user["id"])})
    return {"access_token": token, "token_type": "bearer"}
```

### Pattern 6: DB Init in Lifespan
**What:** Call `await init_db()` inside the existing lifespan context manager.
**Example:**
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    global orchestrator
    await init_db()           # ADD THIS LINE
    api_key = os.getenv("OPENAI_API_KEY", "demo-key")
    orchestrator = HiveOrchestrator(api_key)
    orchestrator.set_broadcast_callback(manager.broadcast)
    print("Isomorph Office started!")
    yield
    print("Shutting down...")
```

### Anti-Patterns to Avoid
- **Validating WebSocket token after accept:** Always decode the JWT before `await websocket.accept()`. If you accept first, the connection is established and closing it sends a disconnect event to the client instead of a clean auth rejection.
- **Using OAuth2PasswordBearer for WebSocket:** `OAuth2PasswordBearer` expects Authorization header — browsers can't set headers on WebSocket connections. Use `Query(...)` instead.
- **Storing user_id as int in JWT sub:** JWT `sub` claim is conventionally a string. Store `str(user_id)` and convert back to int when needed.
- **Hardcoding SECRET_KEY:** Must come from `.env`. Rotating it invalidates all existing tokens — fine for MVP since no refresh tokens are needed yet.
- **Using `datetime.utcnow()`:** Deprecated in Python 3.12+. Use `datetime.now(timezone.utc)`.
- **Returning hashed password anywhere:** The register endpoint and user queries must strip `hashed_password` from any response body.
- **Connecting aiosqlite on every request:** Pattern above uses `async with aiosqlite.connect()` per call which is acceptable for SQLite at MVP scale. For Phase 3+ with higher load, consider a shared connection or connection pool.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Password hashing | Custom bcrypt wrapper | `passlib.context.CryptContext` | Handles salt, cost factor, legacy hash migration automatically |
| JWT encoding/decoding | Manual base64 + HMAC | `jose.jwt.encode` / `jose.jwt.decode` | Clock skew, exp validation, algorithm pinning handled correctly |
| Bearer token extraction from headers | Manual header parsing | `OAuth2PasswordBearer` + `Depends` | FastAPI generates OpenAPI security scheme; extraction is one-liner |
| Auth middleware for all routes | Custom ASGI middleware | `Depends(get_current_user)` per route | Middleware approach makes it impossible to exclude public routes cleanly; dependency injection is the FastAPI pattern |
| Timing-safe password comparison | `==` string comparison | `pwd_context.verify()` | passlib's verify is timing-safe by design; `==` is vulnerable to timing attacks |

**Key insight:** The three auth operations (hash, verify, encode/decode JWT) are each 1-2 lines with the correct libraries. The complexity is all in subtle security details (timing attacks, salt handling, expiry, algorithm pinning) that these libraries resolve by default.

---

## Common Pitfalls

### Pitfall 1: HTTPBearer Returns 403 Instead of 401
**What goes wrong:** `OAuth2PasswordBearer` and `HTTPBearer` both return HTTP 403 (not 401) when the token is missing or malformed because FastAPI's default behavior is to treat missing credentials as "forbidden" not "unauthorized."
**Why it happens:** FastAPI security schemes raise `HTTPException(403)` by default. AUTH-03 success criteria require 401.
**How to avoid:** In `get_current_user`, explicitly raise `HTTPException(status_code=401, headers={"WWW-Authenticate": "Bearer"})` for all failure paths. Use `OAuth2PasswordBearer(auto_error=False)` to suppress the automatic 403 and handle errors manually.
**Warning signs:** Running `curl /api/agents` without a token and seeing `{"detail":"Not authenticated"}` with 403 status.

### Pitfall 2: WebSocket Auth Token in URL Appears in Server Logs
**What goes wrong:** `/ws?token=<long-jwt>` appears in access logs, giving an attacker who reads the logs a valid JWT.
**Why it happens:** Query parameters are part of the URL and logged by uvicorn/nginx by default.
**How to avoid:** For MVP this is acceptable — log scrubbing is a hardening concern, not a Phase 1 blocker. Document the risk. Mitigation: short token expiry (30 min) limits the exploitation window. Phase 4 hardening can address log scrubbing.
**Warning signs:** uvicorn access logs showing full WS upgrade URLs.

### Pitfall 3: aiosqlite UNIQUE Constraint Raises Generic Exception
**What goes wrong:** Calling `create_user` with a duplicate email raises `aiosqlite.IntegrityError` — if not caught, FastAPI returns an unformatted 500.
**Why it happens:** aiosqlite propagates SQLite constraint errors as Python exceptions, not as structured errors.
**How to avoid:** Explicitly check for existing user with `get_user_by_email` before inserting, OR catch `aiosqlite.IntegrityError` in the register handler and return HTTP 400.
**Warning signs:** `500 Internal Server Error` when registering with a duplicate email.

### Pitfall 4: Lifespan Does Not Call init_db — Table Missing on First Request
**What goes wrong:** If `init_db()` is not called before the first request, `users` table doesn't exist and all auth queries fail with `no such table: users`.
**Why it happens:** SQLite does not create tables automatically; `CREATE TABLE IF NOT EXISTS` only runs if called explicitly.
**How to avoid:** Add `await init_db()` as the first line inside the `lifespan` context manager in `main.py`.
**Warning signs:** `aiosqlite.OperationalError: no such table: users` on first `POST /auth/register`.

### Pitfall 5: JWTError from python-jose vs jwt.exceptions from PyJWT
**What goes wrong:** Mixing `from jose import JWTError` (python-jose) with `from jwt.exceptions import InvalidTokenError` (PyJWT). They are incompatible — installing both creates confusing import errors.
**Why it happens:** Recent FastAPI docs show PyJWT patterns; Stack Overflow answers mix the two.
**How to avoid:** Project is locked to `python-jose[cryptography]`. Use only `from jose import JWTError, jwt`. Never install PyJWT separately.
**Warning signs:** `ImportError: cannot import name 'InvalidTokenError' from 'jose'`.

### Pitfall 6: Two Users Seeing Each Other's Data (AUTH-03 Isolation)
**What goes wrong:** The existing `ConnectionManager` stores connections in `Set[WebSocket]` without any user keying. After auth is added, `broadcast()` still sends to all connected WebSockets — a message for user A reaches user B's browser.
**Why it happens:** `ConnectionManager.broadcast()` iterates `self.active_connections` which is a flat set.
**How to avoid:** In Phase 1, change `active_connections: Set[WebSocket]` to `active_connections: Dict[str, WebSocket]` keyed by `user_id`. Update `connect(websocket, user_id)` and `broadcast_to_user(user_id, message)`. This is a small change but critical for AUTH-03 success criterion 4 ("two users simultaneously cannot see each other's data").
**Warning signs:** User B's browser console shows WebSocket messages intended for user A's pipeline run.

---

## Code Examples

### Complete auth.py Module
```python
# Source: FastAPI official docs (https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/)
# Adapted for python-jose + passlib (project stack)
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME_IN_PRODUCTION")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> dict:
    """FastAPI dependency — inject into any route to require auth."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise credentials_exception
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    return {"user_id": int(user_id)}
```

### WebSocket Auth — Token Before Accept
```python
# Source: https://fastapi.tiangolo.com/advanced/websockets/
# + WebSocket auth pattern from community verification
from fastapi import WebSocket, WebSocketException, status, Query
from jose import JWTError, jwt

@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...)
):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    except JWTError:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    await manager.connect(websocket, user_id=user_id)  # keyed by user_id
    # ... rest of handler
```

### Updated ConnectionManager (tenant-keyed)
```python
# Based on direct inspection of main.py — refactored for per-user routing
from typing import Dict
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}  # user_id -> websocket

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: str):
        self.active_connections.pop(user_id, None)

    async def send_to_user(self, user_id: str, message: dict):
        """Send message to a specific user only."""
        ws = self.active_connections.get(user_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(user_id)

    async def broadcast(self, message: dict):
        """Legacy — send to all. Keep for demo/admin use only."""
        disconnected = []
        for uid, connection in self.active_connections.items():
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(uid)
        for uid in disconnected:
            self.disconnect(uid)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `datetime.utcnow()` for JWT exp | `datetime.now(timezone.utc)` | Python 3.12 deprecated utcnow | Use timezone-aware UTC always |
| `python-jose` + `passlib[bcrypt]` | `PyJWT` + `pwdlib[argon2]` | FastAPI docs updated ~2024 | Project is locked to python-jose + passlib — do not switch; both are production-safe |
| Manual bearer extraction | `OAuth2PasswordBearer(auto_error=False)` + explicit 401 | FastAPI 0.95+ | auto_error=False gives 401 control; True gives 403 |
| `Set[WebSocket]` in ConnectionManager | `Dict[user_id, WebSocket]` | Required for multi-tenant | Flat set is a tenant isolation bug, not a future concern |

**Deprecated/outdated:**
- `datetime.utcnow()`: Deprecated Python 3.12. Use `datetime.now(timezone.utc)`.
- `python-jose` stale note: python-jose had a maintenance concern raised in 2023; it remains functional and is the project-locked choice. Do not swap to PyJWT mid-phase.

---

## Open Questions

1. **SECRET_KEY rotation strategy**
   - What we know: For MVP, a single HS256 key in `.env` is standard and correct
   - What's unclear: If the key is rotated (e.g., compromised), all existing sessions are invalidated — there is no refresh token mechanism (AUTH-04 is v2)
   - Recommendation: Document this in `.env.example` as a warning; it is not a Phase 1 blocker

2. **Email validation strictness on registration**
   - What we know: `str` field accepts anything; `pydantic.EmailStr` requires `email-validator` package
   - What's unclear: Project requirements say "email and password" but do not specify format validation
   - Recommendation: Use plain `str` for MVP register endpoint to avoid adding `email-validator` dependency; add EmailStr validation in Phase 4 hardening

3. **Concurrent WebSocket connections per user**
   - What we know: `Dict[str, WebSocket]` overwrites if the same user connects twice (e.g., two browser tabs)
   - What's unclear: Is multi-tab behavior a Phase 1 concern or a later UX decision?
   - Recommendation: For Phase 1, last-connection-wins is acceptable. Document it. Phase 3 can add `Dict[str, List[WebSocket]]` if needed.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + httpx (AsyncClient for FastAPI) |
| Config file | None — Wave 0 creates `backend/pytest.ini` |
| Quick run command | `cd backend && pytest tests/test_auth.py -x -q` |
| Full suite command | `cd backend && pytest tests/ -x -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AUTH-01 | POST /auth/register returns 201, no password in body | unit | `pytest tests/test_auth.py::test_register_success -x` | Wave 0 |
| AUTH-01 | Duplicate email returns 400 | unit | `pytest tests/test_auth.py::test_register_duplicate_email -x` | Wave 0 |
| AUTH-01 | Raw password not in DB or response | unit | `pytest tests/test_auth.py::test_password_not_stored_plain -x` | Wave 0 |
| AUTH-02 | POST /auth/login with valid creds returns signed JWT | unit | `pytest tests/test_auth.py::test_login_returns_jwt -x` | Wave 0 |
| AUTH-02 | POST /auth/login with wrong password returns 401 | unit | `pytest tests/test_auth.py::test_login_wrong_password -x` | Wave 0 |
| AUTH-03 | GET /api/agents without token returns 401 | unit | `pytest tests/test_auth.py::test_protected_route_no_token -x` | Wave 0 |
| AUTH-03 | WebSocket /ws without token is rejected | unit | `pytest tests/test_auth.py::test_websocket_no_token_rejected -x` | Wave 0 |
| AUTH-03 | Two users cannot see each other's WS messages | integration | `pytest tests/test_auth.py::test_tenant_isolation -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && pytest tests/test_auth.py -x -q`
- **Per wave merge:** `cd backend && pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `backend/tests/__init__.py` — empty init
- [ ] `backend/tests/test_auth.py` — all 8 test cases above
- [ ] `backend/tests/conftest.py` — shared `async_client` fixture using `httpx.AsyncClient` + `ASGITransport`
- [ ] `backend/pytest.ini` — `asyncio_mode = auto`
- [ ] Framework install: `pip install pytest pytest-asyncio httpx`

---

## Sources

### Primary (HIGH confidence)
- FastAPI official docs — OAuth2 + JWT: https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/
- FastAPI official docs — WebSockets: https://fastapi.tiangolo.com/advanced/websockets/
- Direct code inspection — `backend/main.py`, `backend/models.py`, `backend/orchestrator.py` — confirmed flat ConnectionManager, zero existing auth, existing lifespan pattern
- `backend/requirements.txt` — confirmed current installed versions (fastapi 0.109, pydantic 2.5.3, no aiosqlite/jose/passlib yet)

### Secondary (MEDIUM confidence)
- TestDriven.io FastAPI JWT guide: https://testdriven.io/blog/fastapi-jwt-auth/ — verified patterns against official docs
- DEV Community WebSocket auth pattern: https://dev.to/hamurda/how-i-solved-websocket-authentication-in-fastapi-and-why-depends-wasnt-enough-1b68 — validated WebSocket query param approach matches official docs
- FastAPI GitHub discussion #9130 — confirmed HTTPBearer 403 vs 401 behavior

### Tertiary (LOW confidence)
- aiosqlite direct query patterns — training data, cross-checked with aiosqlite 0.20.x API; no contradictions found but no Context7 verification performed

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — python-jose, passlib, aiosqlite are explicit project constraints; verified against official FastAPI docs
- Architecture: HIGH — all patterns verified against official FastAPI JWT and WebSocket docs; code examples are from primary sources
- Pitfalls: HIGH — flat ConnectionManager (Pitfall 6), missing init_db call (Pitfall 4), and 403/401 behavior (Pitfall 1) confirmed by direct code inspection + official docs; not speculative
- WebSocket auth: HIGH — query parameter pattern confirmed by official FastAPI docs + community verification

**Research date:** 2026-03-17
**Valid until:** 2026-09-17 (stable stack; python-jose/passlib are not fast-moving)
