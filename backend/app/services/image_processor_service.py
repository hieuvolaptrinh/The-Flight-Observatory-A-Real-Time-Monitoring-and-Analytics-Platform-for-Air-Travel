import cv2
import numpy as np
import io
import os
from datetime import datetime
from PIL import Image, ExifTags


# TEST LƯU IMG XỬ LÝ Ở ROOT
OUTPUT_DIR = "processed_images"


# rotate → resize - normalize_light,edge_detection,morphological_close  → detect receipt → perspective → grayscale → denoise
class ImageProcessorService:
    def __init__(self):
        os.makedirs(OUTPUT_DIR, exist_ok=True)  ## tự tạo folder nếu chưa có

    def process(self, image_bytes: bytes) -> dict:
        steps = []

        img = self._decode(image_bytes)
        img = self._correct_orientation(img, image_bytes)
        steps.append("orientation")

        img = self._resize(img)
        steps.append("resize")

        gray = self._normalize_light(img)  # grayscale + CLAHE
        steps.append("normalize_light")

        denoised = self._denoise(gray)
        steps.append("denoise")

        edges = self._detect_edges(denoised)  # Adaptive Canny
        steps.append("edge_detection")

        closed = self._morphological_close(edges)  # nối cạnh đứt
        steps.append("morphological_close")

        crop_result = self._find_and_crop(img, closed)
        was_cropped = crop_result["success"]
        crop_confidence = crop_result["confidence"]
        cropped_img = crop_result["image"]
        if was_cropped:
            steps.append("perspective_crop")

        final_img = self._preprocess_for_ocr(cropped_img)
        steps.append("preprocess_ocr")

        saved_path = self._save(final_img)  # debug

        _, encoded = cv2.imencode(".png", final_img)
        processed_bytes = encoded.tobytes()

        return {
            "processed_image_bytes": processed_bytes,
            "was_cropped": was_cropped,
            "crop_confidence": round(crop_confidence, 3),
            "steps_applied": steps,
            "debug_path": saved_path,
        }

    # step 0: decode
    def _decode(self, image_byte: bytes) -> np.ndarray:
        arr = np.frombuffer(image_byte, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)  ## giải nén ra để đọc
        if img is None:
            raise ValueError("unable read this image")
        return img

    #  step 2: resize image
    def _resize(self, img: np.ndarray) -> np.ndarray:
        MAX_DIM = 1280
        h, w = img.shape[:2]
        if max(h, w) <= MAX_DIM:
            return img

        scale = MAX_DIM / max(h, w)
        return cv2.resize(img, None, fx=scale, fy=scale)

    # step 1 : rotate image  -> vì ảnh chụp nó đã qua bước resize nên phải sử dụng exif để check orientation,
    def _correct_orientation(self, img: np.ndarray, raw_bytes: bytes) -> np.ndarray:
        try:
            pil_img = Image.open(io.BytesIO(raw_bytes))
            exif = pil_img._getexif()
            if exif is None:
                return img

            # tìm key xem thử có oritentation ko
            orientation_key = next(
                (k for k, v in ExifTags.TAGS.items() if v == "Orientation"), None
            )
            if orientation_key not in exif:
                return img

            orientation = exif[orientation_key]
            rotation_map = {3: 180, 6: 270, 8: 90}
            angle = rotation_map.get(orientation)
            if angle:
                h, w = img.shape[:2]
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, -angle, 1.0)
                img = cv2.warpAffine(img, M, (w, h))
        except Exception:
            pass
        return img

    def _normalize_light(self, img: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(
            clipLimit=3.0, tileGridSize=(8, 8)
        )  # tương phản 3 tránh trường hợp điện thoại cùi chụp bị mờ ko rõ chói
        return clahe.apply(gray)

    def _denoise(self, gray: np.ndarray) -> np.ndarray:
        return cv2.GaussianBlur(gray, (3, 3), 0)

    def _detect_edges(self, gray: np.ndarray) -> np.ndarray:
        median_val = np.median(gray)
        lower = int(max(0, 0.67 * median_val))
        upper = int(min(255, 1.33 * median_val))
        return cv2.Canny(gray, lower, upper)

    # nối cạnh bị đứt
    def _morphological_close(self, edges: np.ndarray) -> np.ndarray:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        return cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

    def _find_and_crop(
        self, original_img: np.ndarray, closed_edges: np.ndarray
    ) -> dict:
        img_area = original_img.shape[0] * original_img.shape[1]

        contours, _ = cv2.findContours(
            closed_edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if not contours:
            return {"success": False, "confidence": 0.0, "image": original_img}

        candidates = sorted(contours, key=cv2.contourArea, reverse=True)[:15]

        best_score = 0.0
        best_pts = None

        for contour in candidates:
            score, pts = self._score_candidate(contour, img_area)
            if score > best_score:
                best_score = score
                best_pts = pts

        # ngưỡng tối thiểu để chấp nhận crop
        MIN_SCORE = 0.5
        if best_pts is None or best_score < MIN_SCORE:
            return {"success": False, "confidence": best_score, "image": original_img}

        warped = self._four_point_transform(original_img, best_pts)

        # Validate crop
        if not self._validate_crop(warped, img_area):
            return {"success": False, "confidence": best_score, "image": original_img}

        return {"success": True, "confidence": best_score, "image": warped}

    # chấm điểm candidate để chọn
    def _score_candidate(self, contour, img_area: int):
        area = cv2.contourArea(contour)
        if area < img_area * 0.10:
            return 0.0, None
        # 1: diện tích so với ảnh (0.0 - 0.3 điểm)
        area_ratio = area / img_area
        score = 0.0
        score += min(area_ratio * 2, 0.3)  # max 0.3 khi chiếm >= 15% ảnh
        #   2: độ lồi - convexity (0.0 - 0.2 điểm)
        hull = cv2.convexHull(contour)
        hull_area = cv2.contourArea(hull)
        if hull_area > 0:
            convexity = area / hull_area
            if convexity >= 0.85:
                score += 0.2
        #  3: hình chữ nhật - rectangularity (0.0 - 0.2 điểm)
        x, y, w, h = cv2.boundingRect(contour)
        rect_area = w * h
        if rect_area > 0:
            rectangularity = area / rect_area
            if rectangularity >= 0.75:
                score += 0.2
        #  4: tỷ lệ chiều dài/rộng hợp lý (0.0 - 0.15 điểm)
        aspect = max(w, h) / max(min(w, h), 1)
        if 1.2 <= aspect <= 8.0:
            score += 0.15
        #  5: approxPolyDP ra 4-8 đỉnh (0.0 - 0.15 điểm)
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
        pts = None
        if len(approx) == 4:
            pts = approx.reshape(4, 2).astype(np.float32)
            score += 0.15
        elif 4 < len(approx) <= 8:
            # Fallback: dùng minAreaRect lấy 4 góc
            rect = cv2.minAreaRect(contour)
            box = cv2.boxPoints(rect)
            pts = box.astype(np.float32)
            score += 0.08  # điểm thấp hơn vì không chắc chắn bằng
        return score, pts

    #  kiểm tra chất lượng sáu khi crop
    def _validate_crop(self, cropped: np.ndarray, original_area: int) -> bool:
        if cropped is None or cropped.size == 0:
            return False

        h, w = cropped.shape[:2]
        crop_area = h * w

        if crop_area < original_area * 0.10:
            return False

        aspect = max(w, h) / max(min(w, h), 1)
        if aspect > 10.0:
            return False
        return True

    def _preprocess_for_ocr(self, img: np.ndarray) -> np.ndarray:
        # grayscale
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img.copy()

        denoised = cv2.GaussianBlur(gray, (3, 3), 0)

        clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(4, 4))
        enhanced = clahe.apply(denoised)
        return enhanced

    # step 3 detech recpit
    def _detect_invoice(self, img: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edge = cv2.Canny(blurred, 75, 200)

        contours, _ = cv2.findContours(edge, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        # sắp xếp theo diện tích lấy 5 phần lớn nhất  vì có thể có ảnh nhiễu
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]

        for contour in contours:
            peri = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
            # lấy vật thể hình chữ nhật nếu ảnh NHIỄU
            if len(approx) == 4:
                pts = approx.reshape(4, 2).astype(np.float32)
                return self._four_point_transform(img, pts)
        return None

    def _order_points(self, pts: np.ndarray) -> np.ndarray:
        rect = np.zeros((4, 2), dtype=np.float32)
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]
        rect[2] = pts[np.argmax(s)]
        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]
        rect[3] = pts[np.argmax(diff)]
        return rect

    def _four_point_transform(self, img: np.ndarray, pts: np.ndarray) -> np.ndarray:
        rect = self._order_points(pts)
        tl, tr, br, bl = rect

        # tính kích thước output
        w = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
        h = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))

        dst_pts = np.array(
            [[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32
        )

        M = cv2.getPerspectiveTransform(rect, dst_pts)
        return cv2.warpPerspective(img, M, (w, h))

    # final step
    def _to_grayscale(self, img: np.ndarray) -> np.ndarray:
        if len(img.shape) == 3:  # chỉ convert nếu còn là ảnh màu
            return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return img

    def _enhance(self, img: np.ndarray) -> np.ndarray:
        denoised = cv2.GaussianBlur(img, (3, 3), 0)
        # tăng contrast cục bộ, tốt hơn equalizeHist cho hóa đơn
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(denoised)

    #  tạm lưu local để test trước
    def _save(self, img: np.ndarray) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"processed_{timestamp}.png"
        path = os.path.join(OUTPUT_DIR, filename)
        cv2.imwrite(path, img)

        return os.path.abspath(path)
