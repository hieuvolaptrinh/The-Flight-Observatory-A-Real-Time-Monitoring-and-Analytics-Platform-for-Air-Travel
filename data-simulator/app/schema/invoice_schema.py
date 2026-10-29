from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.model.invoice import DiscountType, TaxType
from app.model.invoice_item import DiscountTypeItem
from app.model.payment_history import PaymentMethod, PaymentType
from app.model.upcoming_payment import UpcomingPaymentStatus


class InvoiceResponse(BaseModel):
    id: int
    created_at: datetime | None
    updated_at: datetime | None
    url_invoice: UUID
    user_id: int
    client_id: int | None
    template_invoice_id: int | None
    invoice_number: str
    invoice_date: date
    due_date: date | None
    po_number: str | None
    payment_method: str | None
    currency: str
    discount_type: DiscountType
    discount_value: Decimal
    discount_amount: Decimal
    tax_type: TaxType
    tax_value: Decimal
    tax_amount: Decimal
    isInclusiveTaxItem: bool
    subtotal: Decimal
    taxable_amount: Decimal
    total_amount: Decimal
    paid_amount: Decimal
    balance_due: Decimal
    notes: str | None
    is_paid: bool

class InvoiceUserResponse(BaseModel):
    id: int
    created_at: datetime | None
    updated_at: datetime | None
    address: str | None
    secondary_address: str | None
    third_address: str | None
    email: str
    business_name: str | None
    company_size: int | None
    logo_img_url: str | None
    website_url: str | None
    business_owner_name: str | None
    mobile_number: str | None
    phone_number: str
    region: str | None
    tax_number: str | None

class InvoiceClientResponse(BaseModel):
    id: int
    created_at: datetime | None
    updated_at: datetime | None
    user_id: int
    client_name: str
    email: str | None
    secondary_emails: str | None
    mobile_number: str | None
    phone_number: str | None
    fax: str | None

class TemplateInvoiceResponse(BaseModel):
    id: int
    created_at: datetime | None
    updated_at: datetime | None
    name: str
    description: str | None
    preview_image_url: str | None
    discount_type: DiscountType
    discount_value: Decimal
    discount_amount: Decimal
    tax_type: TaxType
    tax_amount: Decimal
    config: dict[str, Any]

class InvoiceItemResponse(BaseModel):
    id: int
    created_at: datetime | None
    updated_at: datetime | None
    invoice_id: int
    item_name: str
    description: str | None
    unit: str | None
    quantity: Decimal
    unit_cost: Decimal
    subtotal: Decimal
    tax_value: Decimal
    tax_amount: Decimal
    is_taxable: bool
    discount_type: DiscountTypeItem
    discount_value: Decimal
    discount_amount: Decimal
    total: Decimal

class PaymentHistoryResponse(BaseModel):
    id: int
    created_at: datetime | None
    updated_at: datetime | None
    invoice_id: int
    payment_type: PaymentType
    payment_method: PaymentMethod
    amount: Decimal
    notes: str | None
    paid_at: datetime

class UpcomingPaymentResponse(BaseModel):
    id: int
    created_at: datetime | None
    updated_at: datetime | None
    invoice_id: int
    name: str
    payment_method: PaymentMethod
    payment_type: PaymentType
    amount: Decimal
    calculated_amount: Decimal
    paid_amount: Decimal
    due_date: date
    status: UpcomingPaymentStatus
    paid_at: datetime | None
    notes: str | None

class CreateInvoiceResponse(BaseModel):
    invoice: InvoiceResponse
    user: InvoiceUserResponse
    client: InvoiceClientResponse | None
    template_invoice: TemplateInvoiceResponse | None
    items: list[InvoiceItemResponse] = Field(default_factory=list)
    payment_history: list[PaymentHistoryResponse] = Field(default_factory=list)
    upcoming_payments: list[UpcomingPaymentResponse] = Field(default_factory=list)
