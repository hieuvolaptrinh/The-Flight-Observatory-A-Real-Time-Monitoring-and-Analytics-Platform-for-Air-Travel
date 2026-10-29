from contextlib import AbstractContextManager
from typing import Callable

from requests import session
from sqlalchemy.orm import Session

from app.core.exceptions_handler import NotFoundError
from app.model.client import Client
from app.model.invoice import Invoice
from app.model.invoice_item import InvoiceItem
from app.model.payment_history import PaymentHistory
from app.model.template_invoice import TemplateInvoice
from app.model.upcoming_payment import UpcomingPayment
from app.model.user import User


# session.query(...)    # Đọc dữ liệu
# session.add(...)      # Đưa object mới vào phiên
# session.commit()      # Lưu thay đổi thật xuống database
# session.rollback()    # Hủy thay đổi nếu lỗi
# session.refresh(...)  # Đọc lại dữ liệu mới nhất


class InvoiceRepository:
    def __init__(
        self,
        session_factory: Callable[..., AbstractContextManager[Session]],
    ):
        self.session_factory = session_factory

    def create_empty(self, user_id: int, invoice_number: str) -> int:
        with self.session_factory() as session:
            user = session.query(User).filter(User.id == user_id).first()
            if user is None:
                raise NotFoundError(detail="User not found")

            invoice = Invoice(
                user_id=user_id,
                invoice_number=invoice_number,
            )
            session.add(invoice)
            session.commit()
            session.refresh(invoice)
            return invoice.id

    def get_full_detail(self, invoice_id: int, user_id: int) -> dict:
        with self.session_factory() as session:
            invoice = (
                session.query(Invoice)
                .filter(
                    Invoice.id == invoice_id,
                    Invoice.user_id == user_id,
                )
                .first()
            )
            if invoice is None:
                raise NotFoundError(detail="Invoice not found")

            user = session.query(User).filter(User.id == invoice.user_id).first()
            client = None
            if invoice.client_id is not None:
                client = (
                    session.query(Client).filter(Client.id == invoice.client_id).first()
                )

            template_invoice = None
            if invoice.template_invoice_id is not None:
                template_invoice = (
                    session.query(TemplateInvoice)
                    .filter(TemplateInvoice.id == invoice.template_invoice_id)
                    .first()
                )

            items = (
                session.query(InvoiceItem)
                .filter(InvoiceItem.invoice_id == invoice.id)
                .order_by(InvoiceItem.id.asc())
                .all()
            )
            payment_history = (
                session.query(PaymentHistory)
                .filter(PaymentHistory.invoice_id == invoice.id)
                .order_by(PaymentHistory.paid_at.asc())
                .all()
            )
            upcoming_payments = (
                session.query(UpcomingPayment)
                .filter(UpcomingPayment.invoice_id == invoice.id)
                .order_by(UpcomingPayment.due_date.asc())
                .all()
            )

            return {
                "invoice": invoice.model_dump(),
                "user": {
                    "id": user.id,
                    "created_at": user.created_at,
                    "updated_at": user.updated_at,
                    "address": user.address,
                    "secondary_address": user.secondary_address,
                    "third_address": user.third_address,
                    "email": user.email,
                    "business_name": user.business_name,
                    "company_size": user.company_size,
                    "logo_img_url": user.logo_img_url,
                    "website_url": user.website_url,
                    "business_owner_name": user.business_owner_name,
                    "mobile_number": user.mobile_number,
                    "phone_number": user.phone_number,
                    "region": user.region,
                    "tax_number": user.tax_number,
                },
                "client": client.model_dump() if client else None,
                "template_invoice": (
                    template_invoice.model_dump() if template_invoice else None
                ),
                "items": [item.model_dump() for item in items],
                "payment_history": [
                    payment.model_dump() for payment in payment_history
                ],
                "upcoming_payments": [
                    payment.model_dump() for payment in upcoming_payments
                ],
            }
