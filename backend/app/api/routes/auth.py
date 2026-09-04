from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Response

from ...config import settings
from ...services.auth import AuthError, AuthService
from ...services.seed import ensure_starter_watchlist
from .. import schemas
from ..deps import SESSION_COOKIE, CurrentUser, DbSession

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,  # never readable from JavaScript
        samesite="lax",
        secure=settings.environment == "production",
        max_age=settings.session_ttl_days * 86400,
        path="/",
    )


@router.post("/register", response_model=schemas.UserOut, status_code=201)
def register(body: schemas.RegisterRequest, response: Response, db: DbSession):
    try:
        result = AuthService(db).register(str(body.email), body.password, body.display_name)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ensure_starter_watchlist(db, result.user)
    db.commit()
    _set_cookie(response, result.token)
    return result.user


@router.post("/login", response_model=schemas.UserOut)
def login(body: schemas.LoginRequest, response: Response, db: DbSession):
    try:
        result = AuthService(db).login(str(body.email), body.password)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    ensure_starter_watchlist(db, result.user)
    db.commit()
    _set_cookie(response, result.token)
    return result.user


@router.post("/demo", response_model=schemas.UserOut)
def demo(response: Response, db: DbSession):
    """One-click entry for judging. Still a real, persisted user."""
    result = AuthService(db).demo_login()
    ensure_starter_watchlist(db, result.user)
    db.commit()
    _set_cookie(response, result.token)
    return result.user


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    db: DbSession,
    pulse_session: Annotated[str | None, Cookie()] = None,
):
    if pulse_session:
        AuthService(db).logout(pulse_session)
        db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=schemas.UserOut)
def me(user: CurrentUser):
    return user
