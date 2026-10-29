#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesAuthSchemas [1]
#/// Исходный модуль `backend/app/modules/auth/schemas.py` — автоматическая разметка для Obsidian Source Scanner.

import re
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr, field_validator, model_validator

class LoginRequest(BaseModel):
    """Схема для запроса на вход. Поле login — почта или прежний логин."""
    login: str = Field(..., min_length=2, max_length=128)
    password: str = Field(..., min_length=3)


class RegisterRequest(BaseModel):
    """Саморегистрация: логин, почта и пароль. Аккаунт создаётся после кода из письма."""
    login: str = Field(..., min_length=3, max_length=32)
    email: EmailStr = Field(..., max_length=128)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("login", mode="before")
    @classmethod
    def normalize_login(cls, value):
        if not isinstance(value, str):
            return value
        login = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,31}", login):
            raise ValueError("Логин: 3–32 символа, латиница, цифры, точка, _ или -")
        return login

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        if isinstance(value, str):
            return value.strip().lower()
        return value


CONFIRMATION_CODE_REQUIRED = "confirmation_code_required"


class RegisterPendingResponse(BaseModel):
    """Пароль принят, сессии ещё нет. dev_code заполнен только в разработке без SMTP."""
    status: str = CONFIRMATION_CODE_REQUIRED
    email: str
    dev_code: Optional[str] = None


class ConfirmRegisterRequest(BaseModel):
    email: EmailStr = Field(..., max_length=128)
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("code", mode="before")
    @classmethod
    def strip_code(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value


class PasswordForgotRequest(BaseModel):
    login: str = Field(..., min_length=2, max_length=128)


class PasswordForgotResponse(BaseModel):
    status: str = "accepted"
    dev_link: Optional[str] = None


class PasswordResetPreview(BaseModel):
    login: str
    email: str


class PasswordResetConfirm(BaseModel):
    token: str = Field(..., min_length=20, max_length=256)
    password: str = Field(..., min_length=8, max_length=128)


class ResendRegisterRequest(BaseModel):
    email: EmailStr = Field(..., max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        if isinstance(value, str):
            return value.strip().lower()
        return value

class TokenResponse(BaseModel):
    """Схема ответа с токеном"""
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: Optional["UserOut"] = None


class SessionOut(BaseModel):
    """Публичное описание активной сессии (без самого токена)."""
    id: int
    device_label: Optional[str] = None
    geo_label: Optional[str] = None
    ip_masked: Optional[str] = None
    created_at: datetime
    expires_at: datetime
    last_seen_at: Optional[datetime] = None
    is_current: bool = False


class SessionListResponse(BaseModel):
    items: List[SessionOut]

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
