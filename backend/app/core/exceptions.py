#///EPIC Platform.ITEM Core.TOPIC BackendAppCoreExceptions [1]
#/// Исходный модуль `backend/app/core/exceptions.py` — автоматическая разметка для Obsidian Source Scanner.

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from typing import Union, List, Dict, Any
import logging

from app.core.database import looks_like_connectivity_error, try_dispose_pool_on_connectivity_error

logger = logging.getLogger(__name__)


def format_validation_error(errors: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Преобразует ошибки Pydantic в человеко-читаемый формат
    """
    field_errors = {}

    for error in errors:
        # Получаем поле, где произошла ошибка
        loc = error.get("loc", [])
        field = loc[-1] if loc else "unknown"

        # Получаем тип ошибки
        error_type = error.get("type", "unknown")

        # Маппинг типов ошибок на понятные сообщения
        error_messages = {
            "string_too_short": {
                "code": "too_short",
                "message": f"Поле '{field}' должно содержать минимум {error.get('ctx', {}).get('min_length', 'N/A')} символов"
            },
            "string_too_long": {
                "code": "too_long",
                "message": f"Поле '{field}' должно содержать максимум {error.get('ctx', {}).get('max_length', 'N/A')} символов"
            },
            "missing": {
                "code": "required",
                "message": f"Поле '{field}' обязательно для заполнения"
            },
            "string_type": {
                "code": "invalid_type",
                "message": f"Поле '{field}' должно быть строкой"
            },
            "int_parsing": {
                "code": "invalid_number",
                "message": f"Поле '{field}' должно быть числом"
            },
            "value_error": {
                "code": "invalid_value",
                "message": f"Поле '{field}' содержит некорректное значение"
            },
            "email": {
                "code": "invalid_email",
                "message": f"Поле '{field}' должно быть валидным email адресом"
            }
        }

        # Если тип ошибки известен, используем его, иначе общий текст
        if error_type in error_messages:
            field_errors[field] = error_messages[error_type]
        else:
            field_errors[field] = {
                "code": "validation_error",
                "message": error.get("msg", "Ошибка валидации")
            }

    # Если ошибка только по одному полю, возвращаем ее напрямую
    if len(field_errors) == 1:
        field, err = list(field_errors.items())[0]
        return {
            "code": err["code"],
            "description": err["message"],
            "field": field
        }

    # Если ошибок несколько, группируем их
    return {
        "code": "multiple_validation_errors",
        "description": "Проверьте правильность заполнения полей",
        "fields": field_errors
    }


async def validation_exception_handler(
        request: Request,
        exc: Union[RequestValidationError, ValidationError]
) -> JSONResponse:
    """
    Обработчик ошибок валидации
    """
    # Получаем ошибки из исключения
    if isinstance(exc, RequestValidationError):
        errors = exc.errors()
    else:
        errors = exc.errors()

    # Форматируем ошибки
    formatted_error = format_validation_error(errors)

    # Возвращаем красивый ответ
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=formatted_error
    )


async def database_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """
    Возвращает контролируемый ответ при недоступности PostgreSQL вместо ASGI traceback.

    Важно для auth dependencies: Session создаётся лениво, поэтому сетевой timeout может
    случиться уже внутри `get_current_user`, до входа в endpoint handler.
    """
    if looks_like_connectivity_error(exc):
        try_dispose_pool_on_connectivity_error(exc)
        logger.warning(
            "Database connectivity error path=%s method=%s: %s",
            request.url.path,
            request.method,
            exc,
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "code": "database_unavailable",
                "description": "Database is temporarily unavailable. Please retry shortly.",
            },
            headers={"Retry-After": "5"},
        )

    logger.exception(
        "Unhandled database error path=%s method=%s",
        request.url.path,
        request.method,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "code": "database_error",
            "description": "Internal database error",
        },
    )