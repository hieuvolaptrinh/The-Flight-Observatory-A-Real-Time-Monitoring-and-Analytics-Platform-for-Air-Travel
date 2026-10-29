from decimal import Decimal
from enum import Enum

from sqlalchemy import Column, Numeric
from sqlmodel import Field

from app.model.base_model import BaseModel


class DiscountTypeItem(str, Enum):
    PERCENTAGE = "PERCENTAGE"
    FIXED_AMOUNT = "FIXED_AMOUNT"


class InvoiceItem(BaseModel, table=True):
    __tablename__ = "invoice_item"

    invoice_id: int = Field(
        foreign_key="invoice.id",
        nullable=False,
        index=True,
        ondelete="CASCADE",
    )
    item_name: str = Field(max_length=255)
    description: str | None = Field(default=None)
    unit: str | None = Field(
        default=None,
        max_length=50,
    )
    quantity: Decimal = Field(
        default=Decimal("1"),
        sa_column=Column(Numeric(18, 3), nullable=False),
    )
    unit_cost: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(18, 2), nullable=False),
    )
    subtotal: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(18, 2), nullable=False),
    )

    # Item tax is percentage only.
    tax_value: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(5, 2), nullable=False),
    )
    tax_amount: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(18, 2), nullable=False),
    )
    is_taxable: bool = Field(default=False)

    discount_type: DiscountTypeItem = Field(
        default=DiscountTypeItem.FIXED_AMOUNT,
    )
    discount_value: Decimal = Field(default=Decimal("0"))
    discount_amount: Decimal = Field(default=Decimal("0"))
    total: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(18, 2), nullable=False),
    )
