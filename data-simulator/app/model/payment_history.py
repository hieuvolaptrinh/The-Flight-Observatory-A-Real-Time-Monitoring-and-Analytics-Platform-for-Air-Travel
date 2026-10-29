from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from sqlalchemy import CheckConstraint, Column, Numeric, String
from sqlmodel import Field

from app.model.base_model import BaseModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PaymentType(str, Enum):
    PERCENT = "PERCENT"
    FLAT_AMOUNT = "FLAT_AMOUNT"


class PaymentMethod(str, Enum):
    BANK_TRANSFER = "BANK_TRANSFER"
    CARD = "CARD"
    CASH = "CASH"
    CHECK = "CHECK"
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"
    MOBILE_PAYMENT = "MOBILE_PAYMENT"
    OTHER = "OTHER"


class PaymentHistory(BaseModel, table=True):
    __tablename__ = "payment_history"
    __table_args__ = (
        CheckConstraint(
            "amount > 0",
            name="ck_payment_history_amount_positive",
        ),
    )

    invoice_id: int = Field(
        foreign_key="invoice.id",
        nullable=False,
        index=True,
        ondelete="CASCADE",
    )
    payment_type: PaymentType = Field(
        default=PaymentType.FLAT_AMOUNT,
        sa_column=Column(String(30), nullable=False),
    )
    payment_method: PaymentMethod = Field(
        default=PaymentMethod.BANK_TRANSFER,
        sa_column=Column(String(30), nullable=False),
    )
    amount: Decimal = Field(
        sa_column=Column(Numeric(18, 2), nullable=False),
    )
    notes: str | None = Field(default=None)
    paid_at: datetime = Field(default_factory=utc_now, nullable=False)
