#!/usr/bin/env python
"""
Единый скрипт для запуска бэкенда.
Использует прямой импорт вместо subprocess для надежности.
"""
import argparse
import asyncio
import os
import socket
import sys
import subprocess
import time
from pathlib import Path

# Добавляем путь к backend в sys.path
backend_path = Path(__file__).parent
root_path = backend_path.parent

sys.path.insert(0, str(backend_path))

print(f"Root path: {root_path}")
print(f"Backend path: {backend_path}")
print(f"Python path: {sys.path[0]}")

def run_migrations():
    """Запуск миграций через прямой импорт alembic"""
    print("\n[INFO] Applying database migrations...")

    try:
        # Импортируем alembic внутри функции
        from alembic.config import Config
        from alembic import command

        # Путь к alembic.ini в корне проекта
        alembic_ini_path = root_path / "alembic.ini"
        print(f"[INFO] Alembic config: {alembic_ini_path}")

        if not alembic_ini_path.exists():
            print(f"[ERR] alembic.ini not found at {alembic_ini_path}")
            return False

        # Создаем конфиг
        alembic_cfg = Config(str(alembic_ini_path))

        # Применяем миграции
        command.upgrade(alembic_cfg, "head")

        print("[OK] Migrations applied successfully")
        return True

    except ImportError as e:
        print(f"[ERR] Import error: {e}")
        print("   Make sure alembic is installed: pip install alembic")
        return False
    except Exception as e:
        print(f"[ERR] Migration failed: {e}")
        return False

def run_server():
    """Запуск API-сервера через uvicorn"""
    print("\n[START] Starting API server...")
    try:
        import uvicorn
        print("API: http://localhost:8000")
        print("Docs: http://localhost:8000/docs")
        print("Live WS: python backend/run.py ws (port from WS_PORT)")
        print("Workers: python backend/run.py worker --lane heavy|portfolio")
        print("\nPress Ctrl+C to stop\n")
        uvicorn.run(
            "app.main:create_api_app",
            factory=True,
            host="0.0.0.0",
            port=8000,
            reload=False,
            log_level="info",
        )
    except ImportError as e:
        print(f"[ERR] Import error: {e}")
        sys.exit(1)


def run_ws():
    """Запуск WebSocket gateway (отдельный процесс)."""
    from app.core.config import settings
    print("\n[START] Starting Live WS gateway...")
    try:
        import uvicorn
        port = int(settings.WS_PORT)
        print(f"WS: ws://localhost:{port}/ws/live")
        print("\nPress Ctrl+C to stop\n")
        uvicorn.run(
            "app.main:create_ws_app",
            factory=True,
            host="0.0.0.0",
            port=port,
            reload=False,
            log_level="info",
        )
    except ImportError as e:
        print(f"[ERR] Import error: {e}")
        sys.exit(1)


def _port_in_use(host: str, port: int) -> bool:
    """True, если порт уже занят (bind не удался)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return True
    return False


def _find_listening_pids(port: int) -> list[int]:
    """Windows: PID процессов, слушающих TCP-порт."""
    if os.name != "nt":
        return []
    try:
        out = subprocess.check_output(
            ["netstat", "-ano"],
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception:
        return []
    pids: list[int] = []
    needle = f":{port}"
    for line in out.splitlines():
        if "LISTENING" not in line or needle not in line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            pid = int(parts[-1])
        except ValueError:
            continue
        if pid not in pids:
            pids.append(pid)
    return pids


def _ensure_ports_free(ports: list[int], *, kill_existing: bool = False) -> None:
    busy: list[tuple[int, list[int]]] = []
    for port in ports:
        if _port_in_use("0.0.0.0", port):
            busy.append((port, _find_listening_pids(port)))

    if not busy:
        return

    if kill_existing and os.name == "nt":
        killed: set[int] = set()
        for port, pids in busy:
            for pid in pids:
                if pid in killed or pid <= 0:
                    continue
                try:
                    subprocess.run(
                        ["taskkill", "/PID", str(pid), "/F"],
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    killed.add(pid)
                    print(f"[INFO] Stopped pid={pid} (was listening on :{port})")
                except Exception as exc:
                    print(f"[WARN] Failed to stop pid={pid}: {exc}")
        time.sleep(0.5)
        still_busy = [p for p in ports if _port_in_use("0.0.0.0", p)]
        if not still_busy:
            return
        busy = [(p, _find_listening_pids(p)) for p in still_busy]

    lines = ["[ERR] Ports already in use:"]
    for port, pids in busy:
        pid_txt = ", ".join(str(p) for p in pids) if pids else "unknown"
        lines.append(f"  - :{port} (pid: {pid_txt})")
    lines.append("Stop the previous backend run (Ctrl+C in that terminal) or run:")
    lines.append("  python backend/run.py all --kill-ports")
    raise SystemExit("\n".join(lines))


def run_all(skip_migrate: bool = False, kill_ports: bool = False):
    """Запуск всего: API + 2 workers + WS gateway."""
    if not skip_migrate:
        if not run_migrations():
            sys.exit(1)

    from app.core.config import settings

    ws_port = int(settings.WS_PORT)
    _ensure_ports_free([8000, ws_port], kill_existing=kill_ports)

    # Важно: не создаём отдельные командные окна при запуске.
    creation_flags = 0

    python = sys.executable
    run_py = str(Path(__file__).resolve())

    def spawn(args: list[str], label: str) -> subprocess.Popen:
        # Миграции уже применены (или пропущены) родительским процессом.
        # В argparse глобальные опции удобнее передавать ПЕРЕД подкомандой.
        cmd = [python, run_py, "--skip-migrate"] + args
        print(f"\n[SPAWN] [{label}] {' '.join(cmd)}")
        return subprocess.Popen(
            cmd,
            cwd=str(root_path),
            creationflags=creation_flags,
        )

    worker_labels = {"Heavy worker", "Portfolio worker"}
    # worker завершился -> перезапуск не чаще чем раз в N секунд
    worker_restart_backoff_sec = 3.0
    # после конфликта lease (exit_code=2) даём heartbeat стать stale, затем перезапуск с --force-lease
    worker_conflict_backoff_sec = 95.0
    worker_force_on_restart = {"Heavy worker": False, "Portfolio worker": False}
    worker_next_restart_at = {"Heavy worker": 0.0, "Portfolio worker": 0.0}
    worker_restart_count = {"Heavy worker": 0, "Portfolio worker": 0}

    def spawn_worker(label: str) -> subprocess.Popen:
        lane = "heavy" if label == "Heavy worker" else "portfolio"
        args = ["worker", "--lane", lane]
        if worker_force_on_restart.get(label):
            args.append("--force-lease")
        return spawn(args, label)

    procs: list[tuple[str, subprocess.Popen]] = []
    try:
        procs.append(("API", spawn(["server"], "API")))
        procs.append(("Heavy worker", spawn_worker("Heavy worker")))
        procs.append(("Portfolio worker", spawn_worker("Portfolio worker")))
        procs.append(("WS", spawn(["ws"], "WS")))

        print("\n[OK] All processes started.")
        print("Нажмите Ctrl+C в этой консоли, чтобы остановить все процессы.")

        # Ждём завершения всех процессов.
        # Не останавливаем остальные при "раннем" exit одного из них,
        # т.к. это часто бывает из-за гонок/портов/моментального завершения.
        stopped = set()
        while True:
            time.sleep(1)
            alive_any = False
            for idx, (label, p) in enumerate(procs):
                rc = p.poll()
                if rc is None:
                    alive_any = True
                    continue
                if label not in stopped:
                    stopped.add(label)
                    print(f"\n[WARN] {label} exited: pid={p.pid} exit_code={rc}")
                if label in worker_labels:
                    now = time.time()
                    if rc == 2:
                        worker_force_on_restart[label] = True
                        worker_next_restart_at[label] = max(
                            worker_next_restart_at[label],
                            now + worker_conflict_backoff_sec,
                        )
                    if now >= worker_next_restart_at[label]:
                        try:
                            new_p = spawn_worker(label)
                            procs[idx] = (label, new_p)
                            worker_restart_count[label] += 1
                            worker_next_restart_at[label] = now + worker_restart_backoff_sec
                            print(
                                f"[HEAL] {label} restarted (attempt={worker_restart_count[label]}, "
                                f"force_lease={worker_force_on_restart[label]})"
                            )
                            if label in stopped:
                                stopped.remove(label)
                            alive_any = True
                        except Exception as exc:
                            worker_next_restart_at[label] = now + worker_restart_backoff_sec
                            print(f"[WARN] Failed to restart {label}: {exc}")
            if not alive_any:
                print("\n[STOP] All subprocesses exited.")
                break
    except KeyboardInterrupt:
        print("\n[STOP] Stopping processes...")
        for _, p in procs:
            try:
                p.terminate()
            except Exception:
                pass
        # Дадим время, потом добьём
        time.sleep(0.5)
        for _, p in procs:
            try:
                p.kill()
            except Exception:
                pass


def check_dependencies():
    """Проверка наличия необходимых модулей"""
    print("\n[INFO] Checking dependencies...")

    try:
        import sqlalchemy
        print(f"[OK] SQLAlchemy: {sqlalchemy.__version__}")
    except ImportError:
        print("[ERR] SQLAlchemy not installed")
        return False

    try:
        import alembic
        print(f"[OK] Alembic: {alembic.__version__}")
    except ImportError:
        print("[ERR] Alembic not installed")
        return False

    try:
        import uvicorn
        print(f"[OK] Uvicorn: installed")
    except ImportError:
        print("[ERR] Uvicorn not installed")
        return False

    try:
        from app.core.config import settings
        print(f"[OK] App config loaded")
        print(f"   DB_HOST: {settings.DB_HOST}")
        print(f"   DB_NAME: {settings.DB_NAME}")
        print(f"   DB_SCHEMA: {settings.DB_SCHEMA}")
    except ImportError as e:
        print(f"[ERR] App config error: {e}")
        return False
    except Exception as e:
        print(f"[ERR] Settings error: {e}")
        return False

    return True

def run_worker(lane: str, *, force_lease: bool = False):
    """Standalone lane worker process."""
    from app.core.logging_config import setup_logging
    from app.core.background_jobs.worker import LANE_HEAVY, LANE_PORTFOLIO, run_standalone_lane_worker
    from app.core.background_jobs.worker_lease import WorkerLeaseConflictError

    setup_logging()
    allowed = {LANE_PORTFOLIO, LANE_HEAVY}
    if lane not in allowed:
        print(f"[ERR] Unknown lane {lane!r}. Use: portfolio, heavy")
        sys.exit(1)

    print(f"\n[START] Starting standalone worker lane={lane}")
    if force_lease:
        print("[WARN] --force-lease: will steal existing lease if present")
    print("Press Ctrl+C to stop\n")
    try:
        asyncio.run(run_standalone_lane_worker(lane, force_lease=force_lease))
    except WorkerLeaseConflictError as exc:
        print(f"\n[ERR] {exc}")
        print("Уже крутится другой worker этой lane на этой БД.")
        print("Остановите его или: python backend/run.py worker --lane", lane, "--force-lease")
        sys.exit(2)
    except KeyboardInterrupt:
        print("\n[STOP] Worker stopped")


def main():
    """Главная функция"""
    parser = argparse.ArgumentParser(description="GAnal Backend Starter")
    parser.add_argument(
        "--skip-migrate",
        action="store_true",
        help="Пропустить применение миграций перед запуском (для multi-process старта).",
    )
    parser.add_argument(
        "--kill-ports",
        action="store_true",
        help="Перед all: завершить процессы, занимающие порты API/WS (8000, WS_PORT).",
    )
    sub = parser.add_subparsers(dest="command")

    worker_parser = sub.add_parser("worker", help="Run standalone lane worker")
    worker_parser.add_argument(
        "--lane",
        required=True,
        choices=["portfolio", "heavy"],
        help="Worker lane to process",
    )
    worker_parser.add_argument(
        "--force-lease",
        action="store_true",
        help="Steal lane lease even if another worker heartbeat is fresh",
    )

    sub.add_parser("server", help="Run API server (default)")
    sub.add_parser("ws", help="Run Live WebSocket gateway")
    sub.add_parser("migrate", help="Apply migrations only")
    sub.add_parser("all", help="Run API + workers + WS gateway")

    args = parser.parse_args()
    command = args.command or "server"
    skip_migrate = bool(getattr(args, "skip_migrate", False))
    kill_ports = bool(getattr(args, "kill_ports", False))

    print("=" * 50)
    print("GAnal Backend Starter")
    print("=" * 50)

    if not check_dependencies():
        print("\n[ERR] Dependency check failed")
        sys.exit(1)

    if command == "migrate":
        if not run_migrations():
            sys.exit(1)
        return

    if command == "worker":
        if not skip_migrate and not run_migrations():
            sys.exit(1)
        run_worker(args.lane, force_lease=bool(getattr(args, "force_lease", False)))
        return

    if command == "ws":
        if not skip_migrate and not run_migrations():
            sys.exit(1)
        run_ws()
        return

    if command == "all":
        run_all(skip_migrate=skip_migrate, kill_ports=kill_ports)
        return

    if not skip_migrate:
        if not run_migrations():
            print("\n[ERR] Migrations failed")
            sys.exit(1)

    run_server()

if __name__ == "__main__":
    main()