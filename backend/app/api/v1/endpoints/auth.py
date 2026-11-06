from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.security import (
    hash_password, verify_password, create_access_token, get_current_user
)
from app.db.session import get_db
from app.models_db.models import AppUser, AuditLog
from app.schemas.schemas import UserCreate, UserOut, TokenOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    if db.query(AppUser).filter(AppUser.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = AppUser(
        email=payload.email,
        full_name=payload.full_name,
        hashed_pw=hash_password(payload.password),
        role="analyst",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(AppUser).filter(AppUser.email == form.username).first()
    if not user or not verify_password(form.password, user.hashed_pw):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Account disabled")
    user.last_login = datetime.now(timezone.utc)
    db.add(AuditLog(user_id=user.id, action="login", resource_type="auth"))
    db.commit()
    return TokenOut(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
def me(current_user: AppUser = Depends(get_current_user)):
    return current_user
