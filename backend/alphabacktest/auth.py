"""Google sign-in and cookie sessions.

Flow: the browser gets a Google ID token (Google Identity Services) and posts it
to `/api/auth/google`. We verify it with Google's public keys, find or create
the user, and set a signed HttpOnly session cookie. `current_user` reads that
cookie for every protected route.

Auth is on only when `GOOGLE_CLIENT_ID` is set. Without it the app runs as a
single shared local user, so a fresh clone still works with no setup.
"""
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .orm import User

log = logging.getLogger("alphabacktest")

router = APIRouter(prefix="/api/auth", tags=["auth"])

LOCAL_USER_EMAIL = "local@alphabacktest.local"
COOKIE_NAME = "session"
SESSION_DAYS = 14


def google_client_id() -> str | None:
    return os.environ.get("GOOGLE_CLIENT_ID") or None


def auth_enabled() -> bool:
    return google_client_id() is not None


def check_config() -> None:
    """Fail at startup, not on the first login, if auth is half-configured."""
    if auth_enabled() and not os.environ.get("SESSION_SECRET"):
        raise RuntimeError("GOOGLE_CLIENT_ID is set but SESSION_SECRET is not. "
                           "Set SESSION_SECRET to a long random string (see README).")
    if not auth_enabled():
        log.warning("GOOGLE_CLIENT_ID not set: login is off and every visitor shares one local user.")


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(os.environ["SESSION_SECRET"], salt="session")


def verify_google_credential(credential: str) -> dict:
    """Return the verified claims of a Google ID token, or raise ValueError."""
    return id_token.verify_oauth2_token(credential, google_requests.Request(), google_client_id(),
                                        clock_skew_in_seconds=10)


class UserOut(BaseModel):
    id: int
    email: str | None
    name: str | None


class GoogleLogin(BaseModel):
    credential: str


def _local_user(db: Session) -> User:
    user = db.scalar(select(User).where(User.email == LOCAL_USER_EMAIL))
    if user is None:
        user = User(email=LOCAL_USER_EMAIL, name="Local user")
        db.add(user)
        db.commit()
    return user


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """The signed-in user, or 401. With auth off, the shared local user.

    Every route that stores user data depends on this, and scopes its queries
    to the user it returns.
    """
    if not auth_enabled():
        return _local_user(db)
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie:
        try:
            user_id = _serializer().loads(cookie, max_age=SESSION_DAYS * 86400)["uid"]
        except (BadSignature, KeyError, TypeError):
            user_id = None
        user = db.get(User, user_id) if user_id is not None else None
        if user is not None:
            return user
    raise HTTPException(401, detail={"error": "not_authenticated", "message": "Please sign in."})


@router.get("/config")
def config():
    """Tells the frontend whether to show sign-in, and with which client ID."""
    return {"googleClientId": google_client_id()}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return UserOut(id=user.id, email=user.email, name=user.name)


@router.post("/google", response_model=UserOut)
def login_google(body: GoogleLogin, response: Response, db: Session = Depends(get_db)):
    if not auth_enabled():
        raise HTTPException(400, detail={"error": "auth_disabled", "message": "Login is not enabled on this server."})
    try:
        claims = verify_google_credential(body.credential)
    except ValueError:
        raise HTTPException(401, detail={"error": "invalid_token", "message": "Google sign-in could not be verified."})
    email, sub = claims.get("email"), claims.get("sub")
    if not email or not sub or not claims.get("email_verified"):
        raise HTTPException(401, detail={"error": "email_unverified", "message": "Your Google email is not verified."})

    user = db.scalar(select(User).where(User.auth_provider == "google", User.auth_provider_id == sub))
    if user is None:
        # An existing row with the same (Google-verified) email is the same person.
        user = db.scalar(select(User).where(User.email == email)) or User(email=email)
        user.auth_provider, user.auth_provider_id = "google", sub
        db.add(user)
    user.email, user.name = email, claims.get("name") or user.name
    db.commit()

    response.set_cookie(
        COOKIE_NAME, _serializer().dumps({"uid": user.id}), max_age=SESSION_DAYS * 86400,
        httponly=True, samesite="lax", path="/",
        secure=os.environ.get("COOKIE_SECURE", "").lower() in ("1", "true", "yes"))
    return UserOut(id=user.id, email=user.email, name=user.name)


@router.post("/logout", status_code=204)
def logout():
    response = Response(status_code=204)
    response.delete_cookie(COOKIE_NAME, path="/")
    return response
