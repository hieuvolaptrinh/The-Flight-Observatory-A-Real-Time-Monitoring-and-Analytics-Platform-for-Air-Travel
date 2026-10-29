from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import CheckConstraint, Column, Numeric, String
from sqlmodel import Field

from app.model.base_model import BaseModel
from app.model.payment_history import PaymentMethod, PaymentType


class UpcomingPaymentStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    OVERDUE = "OVERDUE"


class UpcomingPayment(BaseModel, table=True):
    __tablename__ = "upcoming_payment"
    __table_args__ = (
        CheckConstraint(
            "(payment_type = 'PERCENT' AND amount >= 0 AND amount <= 100) "
            "OR (payment_type = 'FLAT_AMOUNT' AND amount >= 0)",
            name="ck_upcoming_payment_amount",
        ),
    )

    invoice_id: int = Field(
        foreign_key="invoice.id",
        nullable=False,
        index=True,
        ondelete="CASCADE",
    )
    name: str = Field(max_length=255)
    payment_method: PaymentMethod = Field(
        default=PaymentMethod.BANK_TRANSFER,
        sa_column=Column(String(30), nullable=False),
    )
    payment_type: PaymentType = Field(
        default=PaymentType.FLAT_AMOUNT,
        sa_column=Column(String(30), nullable=False),
    )
    amount: Decimal = Field(
        sa_column=Column(Numeric(18, 2), nullable=False),
    )
    calculated_amount: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(18, 2), nullable=False),
    )
    paid_amount: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(18, 2), nullable=False),
    )
    due_date: date = Field(index=True)
    status: UpcomingPaymentStatus = Field(
        default=UpcomingPaymentStatus.SCHEDULED,
        sa_column=Column(String(30), nullable=False, index=True),
    )
    paid_at: datetime | None = Field(default=None)
    notes: str | None = Field(default=None)
