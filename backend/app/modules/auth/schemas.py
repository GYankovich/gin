from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr

class LoginRequest(BaseModel):
    """Схема для запроса на вход"""
    login: str = Field(..., min_length=2, max_length=128)
    password: str = Field(..., min_length=3)

class TokenResponse(BaseModel):
    """Схема ответа с токеном"""
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime

class UserOut(BaseModel):
    """Схема для публичных данных пользователя"""
    id: int
    login: str
    email: Optional[str] = None
    phone: Optional[str] = None

    class Config:
        from_attributes = True
        populate_by_name = True

class UserCreate(BaseModel):
    """Схема для создания пользователя"""
    login: str = Field(..., min_length=3, max_length=128, description="Уникальное имя пользователя")
    password: str = Field(..., min_length=6, description="Пароль (минимум 6 символов)")
    email: Optional[EmailStr] = Field(None, description="Email пользователя")
    phone: Optional[str] = Field(None, description="Телефон пользователя", pattern=r"^\+?[0-9\s\-\(\)]{10,20}$")

    class Config:
        json_schema_extra = {
            "example": {
                "login": "john_doe",
                "password": "secure123",
                "email": "john@example.com",
                "phone": "+79001234567"
            }
        }