import json
import uuid
from datetime import UTC, date, datetime
from typing import Any, ClassVar

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    TypeDecorator,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app import crypto


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware UTC datetimes on every backend (SQLite drops tzinfo)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is not None:
            if value.tzinfo is None:
                raise ValueError("naive datetime")
            value = value.astimezone(UTC)
        return value

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value


class EncryptedText(TypeDecorator[str]):
    """Text encrypted with TOKEN_ENCRYPTION_KEY before it reaches the database."""

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Any) -> bytes | None:
        return None if value is None else crypto.encrypt(value)

    def process_result_value(self, value: bytes | None, dialect: Any) -> str | None:
        return None if value is None else crypto.decrypt(value)


class EncryptedJSON(TypeDecorator[dict[str, Any]]):
    """A JSON document encrypted before it reaches the database."""

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: dict[str, Any] | None, dialect: Any) -> bytes | None:
        if value is None:
            return None
        return crypto.encrypt(json.dumps(value, separators=(",", ":"), ensure_ascii=False))

    def process_result_value(self, value: bytes | None, dialect: Any) -> dict[str, Any] | None:
        return None if value is None else json.loads(crypto.decrypt(value))


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: UTCDateTime,
        dict[str, Any]: JSON,
        list[str]: JSON,
    }


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), default="member")
    # "dark" (default), "light" or "system" (follow the device)
    theme: Mapped[str] = mapped_column(String(10), default="dark", server_default="dark")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    # Set at sign-in and when the session is touched (at most once a minute), so the
    # admin can see who uses the app. Sessions themselves are deleted once idle.
    last_active_at: Mapped[datetime | None]

    passkeys: Mapped[list["Passkey"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class Passkey(Base):
    __tablename__ = "passkeys"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    credential_id: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    public_key: Mapped[bytes] = mapped_column(LargeBinary)
    sign_count: Mapped[int] = mapped_column(default=0)
    transports: Mapped[list[str]] = mapped_column(default=list)
    backed_up: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_used_at: Mapped[datetime | None]

    user: Mapped[User] = relationship(back_populates="passkeys")


class Invite(Base):
    """A one-time link that lets someone set up a passkey for an account."""

    __tablename__ = "invites"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    email: Mapped[str] = mapped_column(String(320))
    display_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), default="member")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]

    def is_pending(self, now: datetime) -> bool:
        return self.used_at is None and self.revoked_at is None and now < self.expires_at


class AuthChallenge(Base):
    """A WebAuthn challenge, deleted as soon as it is used so it can't be replayed."""

    __tablename__ = "auth_challenges"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    purpose: Mapped[str] = mapped_column(String(20))
    challenge: Mapped[bytes] = mapped_column(LargeBinary)
    invite_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("invites.id", ondelete="CASCADE")
    )
    user_handle: Mapped[bytes | None] = mapped_column(LargeBinary)
    expires_at: Mapped[datetime]


class UserSession(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime]

    user: Mapped[User] = relationship()


class AuditEvent(Base):
    """Security events. `detail` must never contain personal data."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    event: Mapped[str] = mapped_column(String(50))
    detail: Mapped[dict[str, Any]] = mapped_column(default=dict)


class Park(Base):
    """An NPS site, cached from the NPS API. Public data shared by everyone, never user-owned."""

    __tablename__ = "parks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    park_code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(Text)
    # "National Park", "National Monument", ... ("Other" when NPS gives none)
    designation: Mapped[str] = mapped_column(Text, index=True)
    # Two-letter state codes, comma separated, e.g. "CA,NV"
    states: Mapped[str] = mapped_column(Text, default="", server_default="")
    latitude: Mapped[float | None]
    longitude: Mapped[float | None]
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    activities: Mapped[list[str]] = mapped_column(default=list)
    # [{"url", "title", "caption", "credit", "alt"}]: shown from NPS's own URLs, never stored
    images: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    url: Mapped[str] = mapped_column(Text, default="", server_default="")
    fetched_at: Mapped[datetime] = mapped_column(default=utcnow)

    @property
    def state_list(self) -> list[str]:
        return [s for s in self.states.split(",") if s]


class ParkRefresh(Base):
    """Progress of loading the park list from NPS (one row, id 1), so a refresh can span requests."""

    __tablename__ = "park_refreshes"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    # "idle", "running", "done" or "failed"
    status: Mapped[str] = mapped_column(String(10), default="idle", server_default="idle")
    started_at: Mapped[datetime | None]
    # When the last attempt ended, successful or not (a failed attempt waits an hour)
    attempted_at: Mapped[datetime | None]
    # When the stored copy was last completely refreshed
    refreshed_at: Mapped[datetime | None]
    next_start: Mapped[int] = mapped_column(default=0, server_default="0")
    total: Mapped[int | None]
    # A short, safe reason (never the API's own text)
    error: Mapped[str | None] = mapped_column(Text)


class FamilyMember(Base):
    """A name offered under "who went". Not a sign-in account; shared by the whole family."""

    __tablename__ = "family_members"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # May be a child's name, so encrypted at rest
    name: Mapped[str] = mapped_column(EncryptedText)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class VisitMember(Base):
    """Who went on a visit. A family member in a visit can't be removed (FR-18)."""

    __tablename__ = "visit_members"

    visit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("visits.id", ondelete="CASCADE"), primary_key=True
    )
    family_member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("family_members.id", ondelete="RESTRICT"), primary_key=True, index=True
    )


class Visit(Base):
    """One trip to a park, in the family's shared log. Any signed-in member can change it."""

    __tablename__ = "visits"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # No cascade: a park NPS drops is kept while the family has a visit to it.
    park_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("parks.id"), index=True)
    visit_date: Mapped[date]
    rating: Mapped[int]  # 1 to 5
    note: Mapped[str | None] = mapped_column(EncryptedText)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    park: Mapped[Park] = relationship()
    members: Mapped[list[FamilyMember]] = relationship(secondary="visit_members")
