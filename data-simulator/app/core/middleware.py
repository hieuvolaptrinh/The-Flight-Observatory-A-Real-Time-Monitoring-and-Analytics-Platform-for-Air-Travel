import json
from functools import wraps

from dependency_injector.wiring import inject as di_inject
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.services.base_service import BaseService


class ResponseFormatMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # OpenAPI JSON phải giữ nguyên cấu trúc để Swagger UI đọc được.
        if request.url.path == request.app.openapi_url:
            return await call_next(request)

        response = await call_next(request)
        content_type = response.headers.get("content-type", "")

        if (
            response.status_code >= 400
            or response.status_code in {204, 304}
            or "application/json" not in content_type
        ):
            return response

        body = b"".join([chunk async for chunk in response.body_iterator])
        data = json.loads(body) if body else None

        # Cho phép endpoint chủ động trả response đã đúng format.
        if isinstance(data, dict) and {"success", "data", "errors"} <= data.keys():
            formatted_data = data
        else:
            formatted_data = {
                "success": True,
                "message": "Success",
                "data": data,
                "errors": None,
            }

        headers = dict(response.headers)
        headers.pop("content-length", None)
        headers.pop("content-type", None)
        return JSONResponse(
            content=formatted_data,
            status_code=response.status_code,
            headers=headers,
            background=response.background,
        )


def inject(func):
    @di_inject
    @wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        injected_services = [
            arg for arg in kwargs.values() if isinstance(arg, BaseService)
        ]
        if injected_services:
            try:
                injected_services[-1].close_scoped_session()
            except Exception as exc:
                logger.error(exc)
        return result

    return wrapper
