#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesAuthSchemas [1]
#/// Исходный модуль `backend/app/modules/auth/schemas.py` — автоматическая разметка для Obsidian Source Scanner.

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr, field_validator, model_validator

class LoginRequest(BaseModel):
    """Схема для запроса на вход"""
    login: str = Field(..., min_length=2, max_length=128)
    password: str = Field(..., min_length=3)

class TokenResponse(BaseModel):
    """Схема ответа с токеном"""
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: Optional["UserOut"] = None

class UserOut(BaseModel):
    """Схема для публичных данных пользователя"""
    id: int
    login: str
    email: Optional[str] = None
    phone: Optional[str] = None
    created_at: Optional[datetime] = None

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


class UserChange(BaseModel):
    """Единый запрос на изменение профиля и/или пароля."""
    login: str = Field(..., min_length=2, max_length=128, description="Логин пользователя")
    email: Optional[EmailStr] = Field(None, description="Email пользователя")
    phone: Optional[str] = Field(None, description="Телефон пользователя", pattern=r"^\+?[0-9\s\-\(\)]{10,20}$")
    current_password: Optional[str] = Field(None, min_length=3, description="Текущий пароль")
    new_password: Optional[str] = Field(None, min_length=3, description="Новый пароль (минимум 3 символа)")

    @field_validator("email", "phone", "current_password", "new_password", mode="before")
    @classmethod
    def empty_str_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_change_rules(self):
        if not self.email and not self.phone:
            raise ValueError("Укажите телефон или email")
        has_password = bool(self.current_password or self.new_password)
        if has_password and (not self.current_password or not self.new_password):
            raise ValueError("Для смены пароля нужны current_password и new_password")
        return self
