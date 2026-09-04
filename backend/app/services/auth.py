"""Authentication.

Deliberately small: opaque random session tokens in an httpOnly cookie, hashed
before storage, with PBKDF2 password hashing from the standard library. No JWT,
because nothing here needs stateless verification and revocation matters more.

The frontend proxies `/api` through Next.js, so the cookie is same-origin and no
token ever touches JavaScript or localStorage.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..config import settings
from ..db.models import User
from ..repositories.users import UserRepository

_ITERATIONS = 210_000
_DEMO_EMAIL = "demo@pulse.market"


class AuthError(Exception):
    pass


@dataclass
class AuthResult:
    user: User
    token: str


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = encoded.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        expected = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(expected.hex(), digest_hex)
    except (ValueError, AttributeError):
        return False


def hash_token(token: str) -> str:
    """Tokens are stored hashed: a leaked database row is not a leaked session."""
    return hmac.new(settings.secret_key.encode(), token.encode(), hashlib.sha256).hexdigest()


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)

    def register(self, email: str, password: str, display_name: str | None = None) -> AuthResult:
        email = email.lower().strip()
        if not email or "@" not in email:
            raise AuthError("Enter a valid email address.")
        if len(password) < 8:
            raise AuthError("Use a password of at least 8 characters.")
        if self.users.by_email(email):
            raise AuthError("An account already exists for that email.")

        user = self.users.create(
            email=email,
            display_name=(display_name or email.split("@")[0]).strip()[:120],
            password_hash=hash_password(password),
        )
        return AuthResult(user, self._issue(user))

    def login(self, email: str, password: str) -> AuthResult:
        user = self.users.by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            # One message for both cases: do not confirm which emails exist.
            raise AuthError("Email or password is incorrect.")
        return AuthResult(user, self._issue(user))

    def demo_login(self) -> AuthResult:
        """One-click entry. Creates the demo account on first use."""
        user = self.users.by_email(_DEMO_EMAIL)
        if user is None:
            user = self.users.create(
                email=_DEMO_EMAIL,
                display_name="Demo",
                password_hash=hash_password(secrets.token_urlsafe(32)),
                is_demo=True,
            )
        return AuthResult(user, self._issue(user))

    def logout(self, token: str) -> None:
        self.users.revoke(hash_token(token))

    def user_for(self, token: str | None) -> User | None:
        if not token:
            return None
        return self.users.user_for_token(hash_token(token))

    def _issue(self, user: User) -> str:
        token = secrets.token_urlsafe(32)
        self.users.create_session(user.id, hash_token(token), settings.session_ttl_days)
        return token


DEMO_EMAIL = _DEMO_EMAIL
