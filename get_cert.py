# get_cert.py
"""Выпуск сертификата Let's Encrypt для ginity.ru.

Порт 80 снаружи закрыт, поэтому проверка идёт через TLS-ALPN-01 на 443.
На время проверки nginx останавливается и затем запускается снова.
"""
import datetime
import socket
import ssl
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from acme import client, messages, challenges, crypto_util, errors
from acmeow.handlers.tls_alpn import generate_tls_alpn_certificate
import josepy as jose

DOMAINS = ["ginity.ru", "www.ginity.ru"]
EMAIL = "admin@ginity.ru"
DIRECTORY_URL = "https://acme-v02.api.letsencrypt.org/directory"

ROOT = Path(__file__).resolve().parent
ACCOUNT_KEY_FILE = ROOT / "account_key.pem"
CERT_FILE = ROOT / "ginity.ru-chain.pem"
PRIVKEY_FILE = ROOT / "ginity.ru-key.pem"
NGINX_DIR = ROOT / "nginx"
NGINX_EXE = NGINX_DIR / "nginx.exe"
NGINX_CONF = NGINX_DIR / "conf" / "nginx.conf"

Ginity_CERT = "C:/Users/GY/WebstormProjects/gin/ginity.ru-chain.pem"
Ginity_KEY = "C:/Users/GY/WebstormProjects/gin/ginity.ru-key.pem"
NEFOR_CERT = "C:/Users/GY/WebstormProjects/gin/nefor.online-chain.pem"
NEFOR_KEY = "C:/Users/GY/WebstormProjects/gin/nefor.online-key.pem"


def generate_rsa_key(key_size=2048):
    return rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
        backend=default_backend(),
    )


def load_or_create_account_key():
    try:
        pem = ACCOUNT_KEY_FILE.read_bytes()
    except FileNotFoundError:
        key = generate_rsa_key()
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        ACCOUNT_KEY_FILE.write_bytes(pem)
    return jose.JWK.load(pem)


def register_account(acme_client):
    try:
        account = acme_client.new_account(
            messages.NewRegistration.from_data(
                email=EMAIL,
                terms_of_service_agreed=True,
            )
        )
        print("[+] Аккаунт зарегистрирован")
        return account
    except errors.ConflictError as exc:
        existing = messages.RegistrationResource(uri=exc.location)
        print("[*] Аккаунт уже существует")
        return acme_client.query_registration(existing)


def port_open(port):
    with socket.socket() as sock:
        sock.settimeout(0.4)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def stop_nginx():
    print("[*] Останавливаем nginx, чтобы занять порт 443")
    subprocess.run([str(NGINX_EXE), "-s", "stop"], cwd=NGINX_DIR, capture_output=True)
    time.sleep(0.5)
    if port_open(443):
        subprocess.run(["taskkill", "/IM", "nginx.exe", "/F"], capture_output=True)
    for _ in range(40):
        if not port_open(443):
            print("[+] Порт 443 свободен")
            return
        time.sleep(0.25)
    raise RuntimeError("nginx не отпустил порт 443")


def start_nginx():
    original = NGINX_CONF.read_text(encoding="utf-8")
    swapped = False
    test = subprocess.run([str(NGINX_EXE), "-t"], cwd=NGINX_DIR, capture_output=True, text=True)
    if test.returncode != 0 and CERT_FILE.exists() is False:
        patched = original.replace(Ginity_CERT, NEFOR_CERT).replace(Ginity_KEY, NEFOR_KEY)
        NGINX_CONF.write_text(patched, encoding="utf-8")
        swapped = True
        test = subprocess.run([str(NGINX_EXE), "-t"], cwd=NGINX_DIR, capture_output=True, text=True)
    if test.returncode != 0:
        if swapped:
            NGINX_CONF.write_text(original, encoding="utf-8")
        print("[-] nginx -t не прошёл")
        print(test.stdout)
        print(test.stderr)
        return False

    subprocess.Popen(
        [str(NGINX_EXE)],
        cwd=NGINX_DIR,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    for _ in range(40):
        if port_open(443):
            break
        time.sleep(0.25)
    if swapped:
        NGINX_CONF.write_text(original, encoding="utf-8")
        print("[*] nginx запущен со старым сертификатом nefor.online")
    else:
        print("[+] nginx запущен")
    return port_open(443)


def challenge_type(challb):
    chall = challb.chall
    if isinstance(chall, challenges.UnrecognizedChallenge):
        return chall.jobj.get("type")
    return getattr(chall, "typ", None)


def challenge_token(challb):
    chall = challb.chall
    if isinstance(chall, challenges.UnrecognizedChallenge):
        return chall.jobj["token"]
    return chall.encode("token")


class AlpnServer:
    def __init__(self, material):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._stop = threading.Event()
        self._thread = None
        self._raw = None
        root = Path(self._tmpdir.name)
        contexts = {}
        for domain, (cert_pem, key_pem) in material.items():
            cert_path = root / f"{domain}.crt"
            key_path = root / f"{domain}.key"
            cert_path.write_bytes(cert_pem)
            key_path.write_bytes(key_pem)
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            ctx.set_alpn_protocols(["acme-tls/1"])
            ctx.load_cert_chain(cert_path, key_path)
            contexts[domain] = ctx

        default_domain = DOMAINS[0]
        self._ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self._ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        self._ctx.set_alpn_protocols(["acme-tls/1"])
        self._ctx.load_cert_chain(root / f"{default_domain}.crt", root / f"{default_domain}.key")

        def sni_callback(sock, server_name, _initial):
            chosen = contexts.get(server_name)
            if chosen is not None:
                sock.context = chosen

        self._ctx.sni_callback = sni_callback

    def start(self):
        raw = socket.socket()
        raw.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        raw.bind(("0.0.0.0", 443))
        raw.listen(32)
        raw.settimeout(1.0)
        self._raw = raw

        def serve():
            while not self._stop.is_set():
                try:
                    conn, _addr = raw.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

        self._thread = threading.Thread(target=serve, daemon=True)
        self._thread.start()

    def _handle(self, conn):
        try:
            tls = self._ctx.wrap_socket(conn, server_side=True)
            tls.settimeout(5)
            try:
                tls.recv(64)
            except Exception:
                pass
            tls.close()
        except Exception:
            try:
                conn.close()
            except Exception:
                pass

    def close(self):
        self._stop.set()
        if self._raw is not None:
            try:
                self._raw.close()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=3)
        self._tmpdir.cleanup()


def self_check(domain):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.set_alpn_protocols(["acme-tls/1"])
    with socket.create_connection(("127.0.0.1", 443), timeout=5) as sock:
        with ctx.wrap_socket(sock, server_hostname=domain) as tls:
            alpn = tls.selected_alpn_protocol()
    if alpn != "acme-tls/1":
        raise RuntimeError(f"ALPN для {domain}: {alpn}")
    print(f"[+] Локальная проверка TLS-ALPN для {domain} прошла")


def get_certificate():
    print(f"[*] Получаем сертификат для {', '.join(DOMAINS)} через TLS-ALPN-01")
    account_key = load_or_create_account_key()
    net = client.ClientNetwork(account_key, user_agent="gin-get-cert")
    directory = messages.Directory.from_json(net.get(DIRECTORY_URL).json())
    acme_client = client.ClientV2(directory, net)
    register_account(acme_client)

    cert_private_key = generate_rsa_key()
    key_pem = cert_private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    csr_pem = crypto_util.make_csr(key_pem, DOMAINS)

    stop_nginx()
    server = None
    try:
        order = acme_client.new_order(csr_pem)
        print("[+] Заказ создан")
        material = {}
        responses = []
        for authz in order.authorizations:
            domain = authz.body.identifier.value
            challb = next(
                (item for item in authz.body.challenges if challenge_type(item) == "tls-alpn-01"),
                None,
            )
            if challb is None:
                offered = [challenge_type(item) for item in authz.body.challenges]
                raise RuntimeError(f"tls-alpn-01 не выдан для {domain}: {offered}")
            http = challenges.HTTP01.from_json(
                {"type": "http-01", "token": challenge_token(challb)}
            )
            key_authz = http.key_authorization(account_key)
            cert_pem, alpn_key = generate_tls_alpn_certificate(domain, key_authz)
            material[domain] = (cert_pem, alpn_key)
            responses.append((challb, http.response(account_key)))

        server = AlpnServer(material)
        server.start()
        for domain in DOMAINS:
            self_check(domain)

        for challb, response in responses:
            acme_client.answer_challenge(challb, response)
        print("[*] Ожидаем проверку Let's Encrypt...")
        deadline = datetime.datetime.now() + datetime.timedelta(seconds=180)
        order = acme_client.poll_and_finalize(order, deadline)
    finally:
        if server is not None:
            server.close()

    if not order.fullchain_pem:
        print(f"[-] Сертификат не выпущен, статус: {order.body.status}")
        return False

    PRIVKEY_FILE.write_bytes(key_pem)
    CERT_FILE.write_text(order.fullchain_pem, encoding="ascii")
    print(f"[+] Сохранён: {CERT_FILE.name}")
    print(f"[+] Сохранён: {PRIVKEY_FILE.name}")
    return True


if __name__ == "__main__":
    ok = False
    try:
        ok = get_certificate()
    except Exception as exc:
        print(f"[-] Ошибка: {exc}")
    finally:
        if not port_open(443):
            start_nginx()
    if ok:
        print("\nСертификаты сохранены:")
        print(f"  - {ACCOUNT_KEY_FILE.name}")
        print(f"  - {PRIVKEY_FILE.name}")
        print(f"  - {CERT_FILE.name}")
    else:
        print("\nНе удалось получить сертификат")
