"""
One-command project startup for Regulatory Intelligence Agent.

Usage:
    python scripts/start.py

Prerequisites:
    1. cp .env.example .env  (fill in API keys)
    2. docker compose up -d

This script:
    1. Health-checks all Docker services (postgres, prometheus, grafana)
    2. Runs Alembic migrations (idempotent)
    3. Starts FastAPI, Streamlit, and the freshness scheduler as supervised subprocesses
    4. Prints a startup summary with all service URLs
    5. Supervises processes — restarts each once on crash, then gives up with a clear error
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
LOGS.mkdir(exist_ok=True)

# ─── Colours ──────────────────────────────────────────────────────────────────

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"


def ok(msg: str) -> None:
    print(f"{GREEN}[OK]{RESET}    {msg}")


def warn(msg: str) -> None:
    print(f"{YELLOW}[WARN]{RESET}  {msg}")


def fatal(msg: str) -> None:
    print(f"{RED}[FATAL]{RESET} {msg}", file=sys.stderr)
    sys.exit(1)


def info(msg: str) -> None:
    print(f"        {msg}")


# ─── Health checks ────────────────────────────────────────────────────────────

def _wait_postgres(retries: int = 5) -> None:
    delay = 2
    for attempt in range(1, retries + 1):
        try:
            conn = psycopg2.connect(
                host=os.environ.get("POSTGRES_HOST", "localhost"),
                port=int(os.environ.get("POSTGRES_PORT", 5432)),
                dbname=os.environ["POSTGRES_DB"],
                user=os.environ["POSTGRES_USER"],
                password=os.environ["POSTGRES_PASSWORD"],
                connect_timeout=5,
            )
            conn.close()
            ok(f"postgres      — healthy (attempt {attempt})")
            return
        except Exception as exc:
            if attempt == retries:
                fatal(
                    f"postgres unreachable after {retries} attempts — "
                    f"check: docker compose logs postgres\n  Last error: {exc}"
                )
            warn(f"postgres not ready (attempt {attempt}/{retries}) — retrying in {delay}s")
            time.sleep(delay)
            delay = min(delay * 2, 30)


def _wait_http(name: str, url: str, retries: int = 5) -> None:
    import urllib.request
    import urllib.error

    delay = 2
    for attempt in range(1, retries + 1):
        try:
            urllib.request.urlopen(url, timeout=5)
            ok(f"{name:<13} — healthy (attempt {attempt})")
            return
        except Exception as exc:
            if attempt == retries:
                fatal(
                    f"{name} unreachable after {retries} attempts — "
                    f"check: docker compose logs {name}\n  Last error: {exc}"
                )
            warn(f"{name} not ready (attempt {attempt}/{retries}) — retrying in {delay}s")
            time.sleep(delay)
            delay = min(delay * 2, 30)


# ─── Migrations ───────────────────────────────────────────────────────────────

def _run_migrations() -> None:
    log_path = LOGS / "migration.log"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    with open(log_path, "w") as f:
        f.write(result.stdout)
        f.write(result.stderr)
    if result.returncode != 0:
        fatal(
            f"Migration failed — see {log_path}\n"
            f"  {result.stderr.strip().splitlines()[-1] if result.stderr.strip() else 'unknown error'}"
        )
    ok("migrations    — up to date")


# ─── Process supervisor ───────────────────────────────────────────────────────

class Process:
    def __init__(self, name: str, cmd: list[str], env: dict | None = None):
        self.name = name
        self.cmd = cmd
        self.env = {**os.environ, **(env or {})}
        self.log_path = LOGS / f"{name}.log"
        self.proc: subprocess.Popen | None = None
        self.restarts = 0

    def start(self) -> None:
        log_fh = open(self.log_path, "a")
        self.proc = subprocess.Popen(
            self.cmd,
            cwd=str(ROOT),
            env=self.env,
            stdout=log_fh,
            stderr=log_fh,
        )

    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def restart_once(self) -> bool:
        """Restart if first crash; return False if already restarted once."""
        if self.restarts >= 1:
            return False
        warn(f"{self.name} died — restarting (see {self.log_path})")
        self.restarts += 1
        self.start()
        return True


PROCESSES = [
    Process(
        name="api",
        cmd=[sys.executable, "-m", "uvicorn", "api.main:app", "--port", "8000"],
    ),
    Process(
        name="ui",
        cmd=[sys.executable, "-m", "streamlit", "run", "ui/app.py", "--server.port", "8501", "--server.headless", "true"],
    ),
    Process(
        name="scheduler",
        cmd=[sys.executable, "-m", "scheduler.freshness"],
    ),
]


def _start_processes() -> None:
    for p in PROCESSES:
        p.start()
        time.sleep(1)  # stagger starts slightly


def _wait_api_ready(retries: int = 10) -> None:
    """Wait for FastAPI to accept connections before declaring it up."""
    import urllib.request
    import urllib.error

    delay = 1
    for attempt in range(1, retries + 1):
        try:
            urllib.request.urlopen("http://localhost:8000/health", timeout=3)
            return
        except Exception:
            time.sleep(delay)
            delay = min(delay * 1.5, 5)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print("\nRegulatory Intelligence Agent — starting up\n")

    # 1. Infrastructure health checks
    _wait_postgres()
    _wait_http("prometheus", "http://localhost:9090/-/ready")
    _wait_http("grafana", "http://localhost:3000/api/health")

    # 2. Migrations
    _run_migrations()

    # 3. Start app processes
    _start_processes()
    _wait_api_ready()

    # 4. Startup summary
    print()
    ok("api           — http://localhost:8000  (docs: http://localhost:8000/docs)")
    ok("ui            — http://localhost:8501")
    ok("scheduler     — nightly delta re-index at 02:00 IST")
    ok("prometheus    — http://localhost:9090")
    ok("grafana       — http://localhost:3000  (admin / admin)")
    print(f"\n        Logs: {LOGS}/\n")

    # 5. Supervisor loop
    print("Supervising processes — Ctrl+C to stop\n")
    try:
        while True:
            for p in PROCESSES:
                if not p.is_alive():
                    restarted = p.restart_once()
                    if not restarted:
                        fatal(
                            f"{p.name} failed twice — not restarting. "
                            f"Check {p.log_path}"
                        )
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nShutting down...")
        for p in PROCESSES:
            if p.proc and p.is_alive():
                p.proc.terminate()
        print("Done.")


if __name__ == "__main__":
    main()
