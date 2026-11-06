import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.config import Settings
from app.core.security import get_current_user
from app.models_db.models import AppUser


def test_production_rejects_dev_auth_bypass():
    """Verify that DEV_AUTH_BYPASS=True is strictly rejected in production."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            DEV_AUTH_BYPASS=True,
            SECRET_KEY="a" * 64,
        )
    assert "DEV_AUTH_BYPASS cannot be enabled in production" in str(exc_info.value)


def test_dev_auth_bypass_returns_transient_analyst(monkeypatch):
    """Verify that when DEV_AUTH_BYPASS is active, an unauthenticated call returns the dev user."""
    from app.core import security
    monkeypatch.setattr(security.settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(security.settings, "DEV_AUTH_BYPASS", True)

    user = get_current_user(token=None)
    assert isinstance(user, AppUser)
    assert user.id == 1
    assert user.role == "analyst"
    assert user.email == "analyst.dev@ueba.local"


def test_disabling_bypass_enforces_authentication(monkeypatch):
    """Verify that when DEV_AUTH_BYPASS is disabled, missing token raises 401."""
    from app.core import security
    monkeypatch.setattr(security.settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(security.settings, "DEV_AUTH_BYPASS", False)

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(token=None)
    assert exc_info.value.status_code == 401
    assert "Not authenticated" in exc_info.value.detail
