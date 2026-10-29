import logging
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def error_response(
    status_code: int,
    message: str,
    errors: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "message": message,
            "data": None,
            "errors": errors,
        },
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = []
    for error in exc.errors():
        location = error.get("loc", ())
        field = ".".join(
            str(part) for part in location if part not in {"body", "query", "path"}
        )
        errors.append(
            {
                "field": field or None,
                "message": error.get("msg", "Invalid value"),
            }
        )

    return error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        message="Invalid request data",
        errors=errors,
    )


async def http_exception_handler(
    request: Request, exc: HTTPException
) -> JSONResponse:
    return error_response(
        status_code=exc.status_code,
        message=str(exc.detail),
        errors=getattr(exc, "errors", None),
    )


async def unexpected_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    logger.exception("Unexpected server error", exc_info=exc)
    return error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message="An internal server error occurred",
    )


class AppError(HTTPException):
    def __init__(self, status_code: int, code: str, detail: str) -> None:
        self.code = code
        super().__init__(status_code=status_code, detail=detail)


class DuplicatedError(AppError):
    def __init__(self, detail: str = "Duplicated data") -> None:
        super().__init__(status.HTTP_400_BAD_REQUEST, "DUPLICATED_ERROR", detail)


class AuthError(AppError):
    def __init__(self, detail: str = "Authentication failed") -> None:
        super().__init__(status.HTTP_403_FORBIDDEN, "AUTH_ERROR", detail)


class NotFoundError(AppError):
    def __init__(self, detail: str = "Resource not found") -> None:
        super().__init__(status.HTTP_404_NOT_FOUND, "NOT_FOUND", detail)


class ValidationError(AppError):
    def __init__(self, detail: str = "Invalid request data") -> None:
        super().__init__(status.HTTP_422_UNPROCESSABLE_ENTITY, "VALIDATION_ERROR", detail)
