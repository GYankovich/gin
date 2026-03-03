#!/usr/bin/env python
"""
Тест проверки пароля пользователя
Запуск: python test_password.py
"""
import sys
from pathlib import Path

# Добавляем путь к backend
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

from app.core.database import SessionLocal
from app.modules.auth.models import User
from app.core.security import verify_password, get_password_hash


def test_user_password(login: str, password: str):
    """
    Проверяет пароль пользователя
    """
    print("=" * 60)
    print(f"🔍 ПРОВЕРКА ПОЛЬЗОВАТЕЛЯ: {login}")
    print("=" * 60)

    db = SessionLocal()

    try:
        # Ищем пользователя
        user = db.query(User).filter(User.login == login).first()

        if not user:
            print(f"❌ Пользователь '{login}' не найден в базе")
            return False

        print(f"✅ Пользователь найден:")
        print(f"   ID: {user.id}")
        print(f"   Login: {user.login}")
        print(f"   Created: {user.created_at}")
        print(f"   Password hash: {user.password_hash[:20]}...")

        # Проверяем пароль
        print(f"\n🔑 Проверка пароля '{password}':")

        is_valid = verify_password(password, user.password_hash)

        if is_valid:
            print(f"   ✅ Пароль правильный!")
            return True
        else:
            print(f"   ❌ Пароль НЕ правильный!")

            # Пробуем другие варианты (на всякий случай)
            print(f"\n🔄 Пробуем другие варианты:")

            # Вариант с другой кодировкой
            variants = [
                password.lower(),
                password.upper(),
                password.strip(),
                password.encode('utf-8').decode('utf-8')
            ]

            # Убираем дубликаты
            variants = list(dict.fromkeys(variants))

            for i, variant in enumerate(variants, 1):
                if variant != password:
                    is_var_valid = verify_password(variant, user.password_hash)
                    if is_var_valid:
                        print(f"   ✅ Вариант {i}: '{variant}' - ПОДХОДИТ!")
                    else:
                        print(f"   ❌ Вариант {i}: '{variant}' - не подходит")

            return False

    except Exception as e:
        print(f"❌ Ошибка при проверке: {e}")
        return False
    finally:
        db.close()
        print("=" * 60)


def create_test_user(login: str, password: str):
    """
    Создает тестового пользователя
    """
    print("\n" + "=" * 60)
    print(f"🆕 СОЗДАНИЕ ТЕСТОВОГО ПОЛЬЗОВАТЕЛЯ: {login}")
    print("=" * 60)

    db = SessionLocal()

    try:
        # Проверяем, существует ли уже
        existing = db.query(User).filter(User.login == login).first()

        if existing:
            print(f"⚠️ Пользователь '{login}' уже существует")
            yn = input("Удалить и создать заново? (y/n): ")

            if yn.lower() == 'y':
                db.delete(existing)
                db.commit()
                print(f"✅ Старый пользователь удален")
            else:
                print(f"❌ Операция отменена")
                return False

        # Хешируем пароль
        password_hash = get_password_hash(password)

        print(f"🔑 Пароль: '{password}'")
        print(f"🔐 Хеш: {password_hash}")

        # Создаем пользователя
        new_user = User(
            login=login,
            password_hash=password_hash
        )
        db.add(new_user)
        db.commit()

        print(f"✅ Пользователь '{login}' успешно создан!")
        return True

    except Exception as e:
        print(f"❌ Ошибка при создании: {e}")
        db.rollback()
        return False
    finally:
        db.close()
        print("=" * 60)


def list_users():
    """
    Показывает всех пользователей
    """
    print("\n" + "=" * 60)
    print("📋 СПИСОК ПОЛЬЗОВАТЕЛЕЙ")
    print("=" * 60)

    db = SessionLocal()

    try:
        users = db.query(User).all()

        if not users:
            print("❌ Нет пользователей в базе")
            return

        for i, user in enumerate(users, 1):
            print(f"\n{i}. ID: {user.id}")
            print(f"   Login: {user.login}")
            print(f"   Created: {user.created_at}")
            print(f"   Hash: {user.password_hash[:30]}...")

    finally:
        db.close()
        print("=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Тест паролей пользователей")
    parser.add_argument("--login", "-l", help="Логин для проверки")
    parser.add_argument("--password", "-p", help="Пароль для проверки")
    parser.add_argument("--create", "-c", action="store_true", help="Создать пользователя")
    parser.add_argument("--list", "-ls", action="store_true", help="Показать всех пользователей")

    args = parser.parse_args()

    if args.list:
        list_users()
    elif args.create and args.login and args.password:
        create_test_user(args.login, args.password)
    elif args.login and args.password:
        test_user_password(args.login, args.password)
    else:
        # Интерактивный режим
        print("🚀 ТЕСТ ПАРОЛЕЙ ПОЛЬЗОВАТЕЛЕЙ")
        print("=" * 60)

        while True:
            print("\nВыберите действие:")
            print("1. Проверить пароль пользователя")
            print("2. Создать нового пользователя")
            print("3. Показать всех пользователей")
            print("4. Выход")

            choice = input("\nВаш выбор (1-4): ").strip()

            if choice == '1':
                login = input("Логин: ").strip()
                password = input("Пароль: ").strip()
                test_user_password(login, password)

            elif choice == '2':
                login = input("Логин: ").strip()
                password = input("Пароль: ").strip()
                create_test_user(login, password)

            elif choice == '3':
                list_users()

            elif choice == '4':
                print("👋 До свидания!")
                break
            else:
                print("❌ Неверный выбор")