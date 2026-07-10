#///EPIC Platform.ITEM Migrations.TOPIC AlembicTest [1]
#/// Исходный модуль `alembic/test.py` — автоматическая разметка для Obsidian Source Scanner.

# test_sqlalchemy.py
import sys
from pathlib import Path

# Добавляем путь к backend
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))
print(f"Добавлен путь к backend: {backend_path}")

print("=" * 50)
print("ШАГ 1: Импортируем настройки")
print("=" * 50)

try:
    from app.core.config import settings
    print(f"✅ Настройки загружены")
    print(f"   Хост: {settings.DB_HOST}")
    print(f"   База: {settings.DB_NAME}")
    print(f"   URL: {settings.DATABASE_URL}")
except Exception as e:
    print(f"❌ Ошибка импорта настроек: {e}")
    sys.exit(1)

print("\n" + "=" * 50)
print("ШАГ 2: Создаем движок SQLAlchemy")
print("=" * 50)

try:
    from sqlalchemy import create_engine, text
    engine = create_engine(settings.DATABASE_URL)
    print(f"✅ Движок создан")
except Exception as e:
    print(f"❌ Ошибка создания движка: {e}")
    sys.exit(1)

print("\n" + "=" * 50)
print("ШАГ 3: Пробуем подключиться к базе")
print("=" * 50)

try:
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))
        print(f"✅ Подключение работает!")
        print(f"   Результат тестового запроса: {result.scalar()}")

        # Проверяем, существует ли схема
        result = connection.execute(
            text(f"SELECT schema_name FROM information_schema.schemata WHERE schema_name = '{settings.DB_SCHEMA}'")
        )
        if result.first():
            print(f"✅ Схема '{settings.DB_SCHEMA}' существует")
        else:
            print(f"⚠️ Схема '{settings.DB_SCHEMA}' НЕ существует")
            # Создаем схему
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{settings.DB_SCHEMA}"'))
            connection.commit()
            print(f"✅ Схема создана")

except Exception as e:
    print(f"❌ Ошибка подключения: {e}")
    sys.exit(1)

print("\n" + "=" * 50)
print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
print("=" * 50)
print("База данных доступна и работает!")