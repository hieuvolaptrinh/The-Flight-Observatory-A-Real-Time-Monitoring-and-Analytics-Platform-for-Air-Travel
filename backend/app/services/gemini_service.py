import json
from google import genai
from google.genai import types
from app.core.config import configs
from app.schema.response.scanbill_response import ScanBillResponse


class GeminiService:
    def __init__(self):
        self.client = genai.Client(api_key=configs.GEMINI_API_KEY)
        self.model = configs.GEMINI_MODEL or "gemini-3.5-flash-lite"

    async def parse_invoice_orc(self, ocr_text: str) -> ScanBillResponse:

        if not ocr_text or not ocr_text.strip():
            return ScanBillResponse()

        prompt = f"""
You are an expert AI for receipt and invoice data extraction.
Extract the merchant and financial information from the OCR text below.

OCR TEXT:
\"\"\"
{ocr_text}
\"\"\"

FIELD DEFINITIONS:
- merchant_name: Name of the store, supermarket, company, or restaurant.
- category_bill: Classify into one of: 'Food & Beverage', 'Supermarket', 'Electronics', 'Fuel', 'Transportation', 'Healthcare', 'Utilities', 'Shopping', 'Other'.
- create_date: Invoice date formatted strictly as 'YYYY-MM-DD' (e.g. 2026-08-20). If not clearly found, return empty string "".
- total_price: Final total amount paid as a pure float number (e.g. 150000.0). Remove all currency symbols, dots used as thousands separators.
- tax: VAT / Tax amount as a pure float number (e.g. 15000.0). Return 0.0 if not found.

OUTPUT FORMAT:
Return a valid JSON object matching these exact keys:
{{
  "merchant_name": "string",
  "category_bill": "string",
  "create_date": "string",
  "total_price": 0.0,
  "tax": 0.0
}}
"""

        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )

            json_str = response.text.strip()
            return ScanBillResponse.model_validate_json(json_str)

        except Exception as e:
            print(f"[GeminiService Error]: {e}")
            return ScanBillResponse()

    async def ask_gemini(self, prompt: str) -> str:

        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            return response.text
        except Exception as e:
            print(f"[GeminiService Error]: {e}")
            return ""
