from datetime import datetime, timedelta, timezone
from typing import Any
import bcrypt
from jose import JWTError, jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models_db import models as db_models

settings = get_settings()
password_hasher = PasswordHasher()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    if hashed.startswith("$argon2"):
        try:
            return password_hasher.verify(hashed, plain)
        except (InvalidHashError, VerificationError, VerifyMismatchError):
            return False
    if hashed.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
        except (ValueError, UnicodeEncodeError):
            return False
    return False


def create_access_token(subject: Any) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return jwt.encode(
        {"sub": str(subject), "exp": expire},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def decode_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        sub: str = payload.get("sub")
        if sub is None:
            raise ValueError("missing sub")
        return sub
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
) -> db_models.AppUser:
    # Development bypass mode: allow direct access without requiring PostgreSQL authentication
    if settings.ENVIRONMENT.lower() != "production" and settings.DEV_AUTH_BYPASS:
        if not token:
            return db_models.AppUser(
                id=1,
                email="analyst.dev@ueba.local",
                full_name="Development Analyst",
                role="analyst",
                is_active=True,
            )
        try:
            user_id = decode_token(token)
            with SessionLocal() as db:
                user = db.get(db_models.AppUser, int(user_id))
                if user and user.is_active:
                    return user
        except Exception:
            return db_models.AppUser(
                id=1,
                email="analyst.dev@ueba.local",
                full_name="Development Analyst",
                role="analyst",
                is_active=True,
            )
        return db_models.AppUser(
            id=1,
            email="analyst.dev@ueba.local",
            full_name="Development Analyst",
            role="analyst",
            is_active=True,
        )

    # Standard production authentication
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = decode_token(token)
    with SessionLocal() as db:
        user = db.get(db_models.AppUser, int(user_id))
        if user is None or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive or missing user")
        return user


def require_role(*roles: str):
    def _checker(current_user: db_models.AppUser = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return current_user
    return _checker
