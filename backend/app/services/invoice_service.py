from datetime import datetime
from uuid import uuid4

from app.repository.invoice_repository import InvoiceRepository


class InvoiceService:
    def __init__(self, invoice_repository: InvoiceRepository):
        self.invoice_repository = invoice_repository

    def create_empty(self, user_id: int) -> dict:
        invoice_number = (
            f"INV-{datetime.now():%Y%m%d}-{uuid4().hex[:6].upper()}"
        )
        invoice_id = self.invoice_repository.create_empty(
            user_id=user_id,
            invoice_number=invoice_number,
        )
        return self.invoice_repository.get_full_detail(
            invoice_id=invoice_id,
            user_id=user_id,
        )
