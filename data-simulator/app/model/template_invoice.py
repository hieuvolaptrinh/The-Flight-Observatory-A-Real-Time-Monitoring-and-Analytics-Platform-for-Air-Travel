from decimal import Decimal
from typing import Any

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.model.base_model import BaseModel
from app.model.invoice import DiscountType, TaxType


class TemplateInvoice(BaseModel, table=True):
    __tablename__ = "template_invoice"

    name: str = Field(
        max_length=255,
        unique=True,
    )
    description: str | None = Field(default=None)
    preview_image_url: str | None = Field(
        default=None,
        max_length=500,
    )
    discount_type: DiscountType = Field(default=DiscountType.NONE)
    discount_value: Decimal = Field(default=Decimal("0"))
    discount_amount: Decimal = Field(default=Decimal("0"))
    tax_type: TaxType = Field(default=TaxType.NONE)
    tax_amount: Decimal = Field(default=Decimal("0"))
    config: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, default=dict),
    )
