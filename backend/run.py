#!/usr/bin/env python
"""
Единый скрипт для запуска бэкенда.
Использует прямой импорт вместо subprocess для надежности.
"""
import sys
from pathlib import Path

# Добавляем путь к backend в sys.path
backend_path = Path(__file__).parent
root_path = backend_path.parent

sys.path.insert(0, str(backend_path))

print(f"📂 Root path: {root_path}")
print(f"📂 Backend path: {backend_path}")
print(f"🐍 Python path: {sys.path[0]}")

def run_migrations():
    """Запуск миграций через прямой импорт alembic"""
    print("\n🔄 Applying database migrations...")

    try:
        # Импортируем alembic внутри функции
        from alembic.config import Config
        from alembic import command

        # Путь к alembic.ini в корне проекта
        alembic_ini_path = root_path / "alembic.ini"
        print(f"📄 Alembic config: {alembic_ini_path}")

        if not alembic_ini_path.exists():
            print(f"❌ alembic.ini not found at {alembic_ini_path}")
            return False

        # Создаем конфиг
        alembic_cfg = Config(str(alembic_ini_path))

        # Применяем миграции
        command.upgrade(alembic_cfg, "head")

        print("✅ Migrations applied successfully")
        return True

    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Make sure alembic is installed: pip install alembic")
        return False
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False

def run_server():
    """Запуск сервера через uvicorn"""
    print("\n🚀 Starting FastAPI server...")

    try:
        import uvicorn

        print(f"🌐 Server will be available at:")
        print(f"   • http://localhost:8000")
        print(f"   • http://127.0.0.1:8000")
        print(f"📚 Docs: http://localhost:8000/docs")
        print(f"\n⏎ Press Ctrl+C to stop\n")

        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=8000,
            reload=False,
            log_level="info"
        )
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Make sure uvicorn is installed: pip install uvicorn")
        sys.exit(1)

def check_dependencies():
    """Проверка наличия необходимых модулей"""
    print("\n🔍 Checking dependencies...")

    try:
        import sqlalchemy
        print(f"✅ SQLAlchemy: {sqlalchemy.__version__}")
    except ImportError:
        print("❌ SQLAlchemy not installed")
        return False

    try:
        import alembic
        print(f"✅ Alembic: {alembic.__version__}")
    except ImportError:
        print("❌ Alembic not installed")
        return False

    try:
        import uvicorn
        print(f"✅ Uvicorn: installed")
    except ImportError:
        print("❌ Uvicorn not installed")
        return False

    try:
        from app.core.config import settings
        print(f"✅ App config loaded")
        print(f"   • DB_HOST: {settings.DB_HOST}")
        print(f"   • DB_NAME: {settings.DB_NAME}")
        print(f"   • DB_SCHEMA: {settings.DB_SCHEMA}")
    except ImportError as e:
        print(f"❌ App config error: {e}")
        return False
    except Exception as e:
        print(f"❌ Settings error: {e}")
        return False

    return True

def main():
    """Главная функция"""
    print("=" * 50)
    print("🚀 GAnal Backend Starter")
    print("=" * 50)

    # Проверяем зависимости
    if not check_dependencies():
        print("\n❌ Dependency check failed")
        sys.exit(1)

    # Запускаем миграции
    if not run_migrations():
        print("\n❌ Migrations failed")
        sys.exit(1)

    # Запускаем сервер
    run_server()

if __name__ == "__main__":
    main()