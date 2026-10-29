import cv2
import numpy as np
from paddleocr import PaddleOCR


class OrcService:
    def __init__(self):
        # PaddleOCR 2.7.x — API ổn định, hỗ trợ tiếng Việt + tiếng Anh + số
        self.ocr = PaddleOCR(
            use_angle_cls=True,  # tự nhận diện text bị nghiêng/ngược
            lang="en",
            use_gpu=False,
            show_log=False,
        )

    def ocr_invoice(self, img_bytes: bytes) -> dict:
        # 1. Decode bytes ảnh đã qua xử lý từ ImageProcessorService
        arr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)

        if img is None:
            raise ValueError("unable decode image")

        # 2. Chạy OCR — PaddleOCR 2.x dùng cls=True
        result = self.ocr.ocr(img, cls=True)

        # 3. Kiểm tra kết quả rỗng
        if not result:
            return {"raw_text": "", "lines": [], "ocr_confidence": 0.0}

        rows = (
            result[0]
            if (
                isinstance(result[0], list)
                and len(result[0]) > 0
                and isinstance(result[0][0], list)
            )
            else result
        )

        if not rows:
            return {"raw_text": "", "lines": [], "ocr_confidence": 0.0}

        lines = []
        confidences = []
        for line_info in rows:
            if line_info is None:
                continue
            text = line_info[1][0].strip()
            confidence = line_info[1][1]
            if text:
                lines.append(text)
                confidences.append(confidence)

        raw_text = "\n".join(lines)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        return {
            "raw_text": raw_text,
            "lines": lines,
            "ocr_confidence": round(avg_confidence, 3),
        }
