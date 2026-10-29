from datetime import date
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import Column, Numeric
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlmodel import Field

from app.model.base_model import BaseModel


class DiscountType(str, Enum):
    NONE = "NONE"
    PERCENTAGE = "PERCENTAGE"
    FIXED_AMOUNT = "FIXED_AMOUNT"


class TaxType(str, Enum):
    NONE = "NONE"
    ON_THE_TOTAL = "ON_THE_TOTAL"
    DEDUCTED = "DEDUCTED"
    PER_ITEM = "PER_ITEM"


class Invoice(BaseModel, table=True):
    __tablename__ = "invoice"

    url_invoice: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(
            PostgreSQLUUID(as_uuid=True),
            unique=True,
            index=True,
            nullable=False,
        ),
    )
    user_id: int = Field(
        foreign_key="users.id",
        nullable=False,
        index=True,
        ondelete="CASCADE",
    )
    client_id: int | None = Field(
        default=None,
        foreign_key="client.id",
        index=True,
        ondelete="SET NULL",
    )
    template_invoice_id: int | None = Field(
        default=None,
        foreign_key="template_invoice.id",
        index=True,
        ondelete="SET NULL",
    )
    invoice_number: str = Field(
        max_length=100,
        index=True,
    )
    invoice_date: date = Field(default_factory=date.today)
    due_date: date | None = Field(default_factory=date.today)
    po_number: str | None = Field(
        default=None,
        max_length=100,
    )
    payment_method: str | None = Field(
        default=None,
        max_length=50,
    )
    currency: str = Field(
        default="USD",
        max_length=10,
    )
    discount_type: DiscountType = Field(default=DiscountType.NONE)
    discount_value: Decimal = Field(default=Decimal("0"))
    discount_amount: Decimal = Field(default=Decimal("0"))
    tax_type: TaxType = Field(default=TaxType.NONE)
    tax_value: Decimal = Field(default=Decimal("0"))
    tax_amount: Decimal = Field(default=Decimal("0"))
    isInclusiveTaxItem: bool = Field(default=False)
    subtotal: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(18, 2), nullable=False),
    )
    taxable_amount: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(18, 2), nullable=False),
    )
    total_amount: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(18, 2), nullable=False),
    )
    paid_amount: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(18, 2), nullable=False),
    )
    balance_due: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(18, 2), nullable=False),
    )
    notes: str | None = Field(default=None)

    signature_url: str | None = Field(
        default=None,
        max_length=255,
    )
    is_paid: bool = Field(default=False)
