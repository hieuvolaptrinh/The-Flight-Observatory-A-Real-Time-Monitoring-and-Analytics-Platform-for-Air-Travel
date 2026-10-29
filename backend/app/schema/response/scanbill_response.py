from typing import Optional
from pydantic import BaseModel, Field


class ScanBillResponse(BaseModel):
    merchant_name: Optional[str] = Field(default="", description="Merchant Name")
    category_bill: Optional[str] = Field(default="", description="Bill Type")
    create_date: Optional[str] = Field(default="", description="Create Date")
    total_price: Optional[float] = Field(default=0, description="Total Price")
    tax: Optional[float] = Field(default=0, description="Tax")
