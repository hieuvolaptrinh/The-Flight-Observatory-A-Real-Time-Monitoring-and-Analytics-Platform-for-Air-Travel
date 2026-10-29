from dependency_injector.wiring import Provide
from fastapi import APIRouter, Depends, File, UploadFile, status
from app.core.container import Container
from app.core.dependencies import get_current_user
from app.core.middleware import inject
from app.model.user import User
from app.schema.invoice_schema import CreateInvoiceResponse
from app.schema.response.scanbill_response import ScanBillResponse
from app.services import GeminiService, ImageProcessorService, InvoiceService, OrcService

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


@router.post("/process-image", response_model=ScanBillResponse)
@inject
async def process_invoice(
    file: UploadFile = File(...),
    img_service: ImageProcessorService = Depends(
        Provide[Container.image_processor_service]
    ),
    orc_service: OrcService = Depends(Provide[Container.orc_service]),
    gemini_service: GeminiService = Depends(Provide[Container.gemini_service]),
):
    image_bytes = await file.read()

    image_result = img_service.process(image_bytes)
    processed_bytes = image_result["processed_image_bytes"]

    ocr_result = orc_service.ocr_invoice(processed_bytes)
    raw_text = ocr_result.get("raw_text", "")

    print(f"[DEBUG OCR Raw Text]:\n{raw_text}")

    return await gemini_service.parse_invoice_orc(raw_text)
