# get_cert.py
import os
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import acme
from acme import client, messages, challenges, crypto_util
from acme import errors
import josepy as jose

# --- НАСТРОЙКИ ---
DOMAIN = "nefor.online"
EMAIL = "admin@nefor.online"
DIRECTORY_URL = "https://acme-v02.api.letsencrypt.org/directory"

ACCOUNT_KEY_FILE = "account_key.pem"
CERT_FILE = "fullchain.pem"
PRIVKEY_FILE = "privkey.pem"

# --- ФУНКЦИИ ДЛЯ РАБОТЫ С КЛЮЧАМИ ---
def generate_rsa_key(key_size=2048):
 """Генерирует RSA-ключ"""
 return rsa.generate_private_key(
 public_exponent=65537,
 key_size=key_size,
 backend=default_backend()
 )

def load_or_create_account_key():
 """Загружает или создаёт ключ аккаунта"""
 try:
 with open(ACCOUNT_KEY_FILE, "rb") as f:
 # Пытаемся загрузить существующий ключ
 key = serialization.load_pem_private_key(
 f.read(),
 password=None,
 backend=default_backend()
 )
 # Конвертируем в JWK
 return jose.JWK(key)
 except (FileNotFoundError, ValueError):
 # Создаём новый ключ
 key = generate_rsa_key()
 jwk = jose.JWK(key)

 # Сохраняем в PEM
 pem = key.private_bytes(
 encoding=serialization.Encoding.PEM,
 format=serialization.PrivateFormat.PKCS8,
 encryption_algorithm=serialization.NoEncryption()
 )
 with open(ACCOUNT_KEY_FILE, "wb") as f:
 f.write(pem)

 return jwk

def create_csr(private_key, domains):
 """Создаёт CSR"""
 from cryptography import x509
 from cryptography.x509.oid import NameOID

 builder = x509.CertificateSigningRequestBuilder()
 builder = builder.subject_name(x509.Name([
 x509.NameAttribute(NameOID.COMMON_NAME, domains[0]),
 ]))

 # Добавляем SAN
 san_list = []
 for domain in domains:
 san_list.append(x509.DNSName(domain))
 builder = builder.add_extension(
 x509.SubjectAlternativeName(san_list),
 critical=False
 )

 csr = builder.sign(private_key, hashes.SHA256(), default_backend())
 return csr

# --- HTTP-СЕРВЕР ДЛЯ HTTP-01 ---
class HTTP01Handler(BaseHTTPRequestHandler):
 def do_GET(self):
 if self.path.startswith('/.well-known/acme-challenge/'):
 token = self.path.split('/')[-1]
 if token in self.server.challenges:
 self.send_response(200)
 self.end_headers()
 self.wfile.write(self.server.challenges[token].encode())
 return
 self.send_response(404)
 self.end_headers()

# --- ГЛАВНАЯ ФУНКЦИЯ ---
def get_certificate():
 print(f"[*] Получаем сертификат для {DOMAIN}...")

 # 1. Загружаем или создаём ключ аккаунта
 account_key = load_or_create_account_key()
 print("[+] Ключ аккаунта готов")

 # 2. Создаём клиент
 net = client.ClientNetwork(account_key)
 acme_client = client.ClientV2(DIRECTORY_URL, net)
 print("[+] Клиент ACME создан")

 # 3. Регистрируем аккаунт
 try:
 account = acme_client.new_account(
 messages.NewRegistration.from_data(
 email=EMAIL,
 terms_of_service_agreed=True,
 )
 )
 print("[+] Аккаунт зарегистрирован")
 except errors.ConflictError:
 print("[*] Аккаунт уже существует")
 except Exception as e:
 print(f"[-] Ошибка регистрации: {e}")
 return False

 # 4. Создаём заказ
 try:
 order = acme_client.new_order(
 messages.NewOrder(
 identifiers=[messages.Identifier(type="dns", value=DOMAIN)],
 )
 )
 print("[+] Заказ создан")
 except Exception as e:
 print(f"[-] Ошибка создания заказа: {e}")
 return False

 # 5. Получаем HTTP-01 проверку
 authz = order.authorizations[0]
 challenge = None
 for ch in authz.body.challenges:
 if isinstance(ch.chall, challenges.HTTP01):
 challenge = ch
 break

 if not challenge:
 print("[-] HTTP-01 не поддерживается")
 return False

 # 6. Запускаем сервер для проверки
 token = challenge.chall.token
 validation = challenge.chall.validation(account_key)

 server = HTTPServer(('0.0.0.0', 80), HTTP01Handler)
 server.challenges = {token: validation}
 thread = threading.Thread(target=server.serve_forever, daemon=True)
 thread.start()

 print(f"[+] HTTP-сервер запущен на порту 80")
 print(f"[*] Токен: {token}")
 print(f"[*] Ожидаем проверку...")

 # 7. Отвечаем на вызов
 try:
 response = challenge.response(account_key)
 acme_client.answer_challenge(challenge, response)
 print("[+] Ответ отправлен")
 except Exception as e:
 print(f"[-] Ошибка: {e}")
 server.shutdown()
 return False

 # 8. Ждём завершения проверки
 retries = 0
 while retries < 30:
 try:
 authz = acme_client.poll(authz)
 if authz.body.status == messages.STATUS_VALID:
 print("[+] Проверка пройдена!")
 break
 elif authz.body.status == messages.STATUS_INVALID:
 print("[-] Проверка не пройдена!")
 server.shutdown()
 return False
 except Exception as e:
 print(f"[*] Ожидание проверки... {e}")
 time.sleep(2)
 retries += 1

 server.shutdown()

 # 9. Генерируем ключ для сертификата
 cert_private_key = generate_rsa_key()
 pem_key = cert_private_key.private_bytes(
 encoding=serialization.Encoding.PEM,
 format=serialization.PrivateFormat.PKCS8,
 encryption_algorithm=serialization.NoEncryption()
 )
 with open(PRIVKEY_FILE, "wb") as f:
 f.write(pem_key)

 # 10. Получаем сертификат
 try:
 csr = create_csr(cert_private_key, [DOMAIN])
 order = acme_client.finalize_order(order, csr)
 time.sleep(2)

 cert = acme_client.poll(order)
 if cert.body.status == messages.STATUS_VALID:
 print("[+] Сертификат получен!")

 # Сохраняем сертификат
 cert_pem = cert.body.fullchain_pem
 with open(CERT_FILE, "w") as f:
 f.write(cert_pem)
 print(f"[+] Сохранён: {CERT_FILE}")
 return True
 else:
 print(f"[-] Статус сертификата: {cert.body.status}")
 return False
 except Exception as e:
 print(f"[-] Ошибка получения сертификата: {e}")
 return False

if __name__ == "__main__":
 if get_certificate():
 print("\n✅ Успешно! Сертификаты сохранены:")
 print(f" - {ACCOUNT_KEY_FILE}")
 print(f" - {PRIVKEY_FILE}")
 print(f" - {CERT_FILE}")
 else:
 print("\n❌ Не удалось получить сертификат")

