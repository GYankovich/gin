import pkgutil
import importlib

print("🔍 Ищем модули с 't' или 'invest' в названии:")
for module in pkgutil.iter_modules():
    if 't' in module.name or 'invest' in module.name:
        print(f"  - {module.name}")

print("\n🔍 Пробуем импортировать по-разному:")

# Вариант 1: как есть
try:
    import t_tech_investments
    print("✅ import t_tech_investments - работает")
    print("   Доступные атрибуты:", [a for a in dir(t_tech_investments) if not a.startswith('_')])
except ImportError as e:
    print(f"❌ import t_tech_investments: {e}")

# Вариант 2: пробуем импортировать Client напрямую
try:
    from t_tech_investments import Client
    print("✅ from t_tech_investments import Client - работает")
except ImportError as e:
    print(f"❌ from t_tech_investments import Client: {e}")

# Вариант 3: пробуем другие возможные имена
try:
    import invest
    print("✅ import invest - работает")
    print("   Доступные атрибуты:", [a for a in dir(invest) if not a.startswith('_')])
except ImportError as e:
    print(f"❌ import invest: {e}")

# Вариант 4: пробуем tinkoff
try:
    import tinkoff
    print("✅ import tinkoff - работает")
    print("   Доступные атрибуты:", [a for a in dir(tinkoff) if not a.startswith('_')])
except ImportError as e:
    print(f"❌ import tinkoff: {e}")

# Вариант 5: пробуем посмотреть, что внутри папки
import os
import sys

package_path = "C:\\Users\\Asus\\AppData\\Local\\Programs\\Python\\Python311\\Lib\\site-packages\\t_tech_investments"
if os.path.exists(package_path):
    print(f"\n📁 Содержимое {package_path}:")
    for item in os.listdir(package_path):
        if item.endswith('.py') or os.path.isdir(os.path.join(package_path, item)):
            print(f"  - {item}")