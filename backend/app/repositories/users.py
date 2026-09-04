from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db.models import AuthSession, User


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def by_email(self, email: str) -> User | None:
        return self.db.scalar(select(User).where(User.email == email.lower().strip()))

    def by_id(self, user_id: int) -> User | None:
        return self.db.get(User, user_id)

    def create(
        self, email: str, display_name: str, password_hash: str, is_demo: bool = False
    ) -> User:
        user = User(
            email=email.lower().strip(),
            display_name=display_name,
            password_hash=password_hash,
            is_demo=is_demo,
            attention_profile={},
        )
        self.db.add(user)
        self.db.flush()
        return user

    # -- sessions -------------------------------------------------------------

    def create_session(self, user_id: int, token_hash: str, ttl_days: int) -> AuthSession:
        session = AuthSession(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=datetime.now(UTC) + timedelta(days=ttl_days),
        )
        self.db.add(session)
        self.db.flush()
        return session

    def user_for_token(self, token_hash: str) -> User | None:
        row = self.db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash))
        if row is None:
            return None
        expires = row.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires < datetime.now(UTC):
            self.db.delete(row)
            self.db.flush()
            return None
        return self.db.get(User, row.user_id)

    def revoke(self, token_hash: str) -> None:
        self.db.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash))
