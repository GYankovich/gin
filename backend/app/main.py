"""
Главный файл FastAPI приложения
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.core.config import settings
from app.core.exceptions import validation_exception_handler
from app.modules.auth.router import router as auth_router
from app.modules.settings.router import router as settings_router

# Создаем приложение
app = FastAPI(
    title="Gin API",
    description="API джина))))",
    version="0.1.0",
    debug=settings.DEBUG,
)

# Подключаем обработчики ошибок
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(ValidationError, validation_exception_handler)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роутеры модулей
app.include_router(auth_router, prefix="/api")
app.include_router(settings_router, prefix="/api")

@app.get("/")
async def root():
    """Корневой эндпоинт для проверки"""
    return {
        "message": "Welcome to Gin API",
        "docs": "/docs",
        "environment": settings.ENVIRONMENT
    }

@app.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    return {"status": "healthy"}