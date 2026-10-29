from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Column, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlmodel import Field

from app.model.base_model import BaseModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SentChannel(str, Enum):
    EMAIL = "EMAIL"
    TEXT = "TEXT"
    COPY_LINK = "COPY_LINK"


class SentHistory(BaseModel, table=True):
    __tablename__ = "sent_history"

    __table_args__ = (
        CheckConstraint(
            "view_count >= 0",
            name="ck_sent_history_view_count_non_negative",
        ),
        CheckConstraint(
            "(invoice_snapshot IS NOT NULL AND snapshot_source_id IS NULL) "
            "OR (invoice_snapshot IS NULL AND snapshot_source_id IS NOT NULL)",
            name="ck_sent_history_snapshot_storage",
        ),
        # Chỉ một SentHistory giữ nội dung gốc cho mỗi phiên bản hóa đơn.
        # Những lần gửi lại không đổi nội dung sẽ trỏ về bản ghi đó.
        Index(
            "uq_sent_history_canonical_snapshot",
            "invoice_id",
            "snapshot_hash",
            unique=True,
            postgresql_where=text("invoice_snapshot IS NOT NULL"),
        ),
    )

    invoice_id: int = Field(
        foreign_key="invoice.id",
        nullable=False,
        index=True,
        ondelete="RESTRICT",
    )

    redirect_token: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(
            PostgreSQLUUID(as_uuid=True),
            unique=True,
            index=True,
            nullable=False,
        ),
    )

    recipient: str | None = Field(
        default=None,
        max_length=255,
        index=True,
    )

    channel: SentChannel = Field(
        default=SentChannel.EMAIL,
        sa_column=Column(
            String(30),
            nullable=False,
        ),
    )

    snapshot_version: int = Field(default=1, nullable=False)

    # SHA-256 của snapshot JSON đã được serialize ổn định (64 ký tự hex).
    snapshot_hash: str = Field(
        max_length=64,
        nullable=False,
        index=True,
    )

    # Chỉ bản gửi đầu tiên của một nội dung hóa đơn giữ JSONB này.
    invoice_snapshot: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )

    # Nếu nội dung không đổi, bản gửi mới chỉ trỏ đến bản giữ snapshot gốc.
    snapshot_source_id: int | None = Field(
        default=None,
        foreign_key="sent_history.id",
        nullable=True,
        index=True,
        ondelete="RESTRICT",
    )

    is_seen: bool = Field(
        default=False,
        index=True,
    )

    sent_at: datetime = Field(
        default_factory=utc_now,
        nullable=False,
    )

    first_seen_at: datetime | None = Field(default=None)

    last_seen_at: datetime | None = Field(default=None)

    view_count: int = Field(default=0, nullable=False)
