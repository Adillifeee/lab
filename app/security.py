import base64
import hashlib
import hmac
import os
import time

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session, select

from app.database.db import get_session
from app.database.models import Role, User

TOKEN_SECRET = os.getenv("TOKEN_SECRET", "development-only-change-me")
bearer = HTTPBearer(auto_error=False)


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240_000)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        salt, expected = encoded.split("$", 1)
        return hmac.compare_digest(hash_password(password, bytes.fromhex(salt)).split("$", 1)[1], expected)
    except (ValueError, TypeError):
        return False


def issue_token(username: str) -> str:
    payload = f"{username}|{int(time.time()) + 8 * 60 * 60}".encode()
    body = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    signature = hmac.new(TOKEN_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> User:
    if not credentials:
        raise HTTPException(401, "Bearer token required", headers={"WWW-Authenticate": "Bearer"})
    try:
        body, signature = credentials.credentials.rsplit(".", 1)
        expected = hmac.new(TOKEN_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("invalid signature")
        payload = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode()
        username, expires = payload.rsplit("|", 1)
        if int(expires) < int(time.time()):
            raise ValueError("expired")
    except (ValueError, TypeError, UnicodeDecodeError):
        raise HTTPException(401, "Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
    user = session.exec(select(User).where(User.username == username, User.is_active == True)).first()  # noqa: E712
    if not user:
        raise HTTPException(401, "User is inactive or does not exist")
    return user


def require_roles(*roles: str):
    def dependency(user: User = Depends(current_user), session: Session = Depends(get_session)) -> User:
        role = session.get(Role, user.role_id)
        if not role or role.name not in roles:
            raise HTTPException(403, "Insufficient role")
        return user
    return dependency
