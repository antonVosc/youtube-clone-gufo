import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.config import settings

_ph = PasswordHasher()
algorithm = "HS256"


def hash_password(p):
    return _ph.hash(p)


def verify_password(p, h):
    try:
        return _ph.verify(h, p)
    except VerifyMismatchError:
        return False


def create_access_token(user_id):
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.access_ttl_min)

    return jwt.encode(
        {"sub": str(user_id), "exp": exp, "typ": "access"},
        settings.jwt_secret,
        algorithm,
    )


def decode_access_token(token):
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=[algorithm])

        if data.get("typ") != "access":
            return None

        return uuid.UUID(data["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        return None


def new_refresh_token():
    raw = secrets.token_urlsafe(48)

    return raw, hash_refresh(raw)


def hash_refresh(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def create_media_token(user_id):
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.media_ttl_min)

    return jwt.encode(
        {"sub": str(user_id), "exp": exp, "typ": "media"},
        settings.jwt_secret,
        algorithm,
    )


def decode_media_token(token):
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=[algorithm])

        return uuid.UUID(data["sub"]) if data.get("typ") == "media" else None
    except (jwt.PyJWTError, ValueError, KeyError):
        return None
