"""
auth.py — JWT and password helpers.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

SECRET_KEY: str = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError(
        "❌ FATAL: SECRET_KEY environment variable not set. "
        "Generate a strong key with: python -c \"import secrets; print(secrets.token_urlsafe(32))\" "
        "and add to .env as SECRET_KEY=<your_key>"
    )
ALGORITHM: str = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))  # Reduced from 24h to 15min

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None
) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
) -> dict:
    """Returns {"user_id": str, "role": str} on success.
    Reads JWT from Authorization header first, then falls back to httpOnly cookie."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    # Try Authorization header first, then ?token= query (for top-level browser
    # redirects like OAuth connect that can't send the header), then cookie.
    if token is None:
        token = request.query_params.get("token")
    if token is None:
        token = request.cookies.get("hive_token")
    if token is None:
        raise credentials_exception
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: Optional[str] = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        role: str = payload.get("role", "client")
    except JWTError:
        raise credentials_exception
    return {"user_id": user_id, "role": role}


async def require_staff(current_user: dict = Depends(get_current_user)) -> dict:
    """Dependency that requires role == 'staff'. Raises 403 otherwise."""
    if current_user.get("role") != "staff":
        raise HTTPException(status_code=403, detail="Staff access required")
    return current_user
