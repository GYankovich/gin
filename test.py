# test_real.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "backend"))

from app.modules.auth.service import auth_service
from app.core.database import SessionLocal
from app.core.config import settings

print("=" * 60)
print("🔍 ТЕСТИРОВАНИЕ ТОКЕНА")
print("=" * 60)

# Вставьте сюда токен из ответа /login
token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwibG9naW4iOiJneSIsImV4cCI6MTc3MjQ2NTAzNX0.fcuN-q8CCA2mqPFdff1OyPR0DlQLCmgOGXDQH-qhaDo"

print(f"\n📝 Тестируем токен: {token[:50]}...")
print(f"🔐 SECRET_KEY: {settings.SECRET_KEY[:20]}...")

db = SessionLocal()
try:
    # Тест 1: Декодируем токен напрямую
    print("\n1. Прямое декодирование токена:")
    from app.core.security import decode_token
    payload = decode_token(token)
    if payload:
        print(f"   ✅ Успех! Payload: {payload}")
    else:
        print("   ❌ Не удалось декодировать")

    # Тест 2: Получаем пользователя через сервис
    print("\n2. Получение пользователя через сервис:")
    user = auth_service.get_user_from_token(db, token)
    if user:
        print(f"   ✅ Успех! Пользователь: {user}")
    else:
        print("   ❌ Пользователь не найден")

finally:
    db.close()
    print("\n" + "=" * 60)