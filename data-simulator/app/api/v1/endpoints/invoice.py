from dependency_injector.wiring import Provide
from fastapi import APIRouter, Depends, status
from app.core.container import Container
from app.core.dependencies import get_current_user
from app.core.middleware import inject
from app.model.user import User
from app.schema.invoice_schema import CreateInvoiceResponse
from app.services import InvoiceService

router = APIRouter(prefix="/invoice", tags=["invoice"])


@router.post(
    "",
    response_model=CreateInvoiceResponse,
    status_code=status.HTTP_201_CREATED,
)
@inject
def create_invoice(
    service: InvoiceService = Depends(Provide[Container.invoice_service]),
    current_user: User = Depends(get_current_user),
):
    return service.create_empty(user_id=current_user.id)
