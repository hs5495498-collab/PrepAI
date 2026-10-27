"""Fixtures for the Selenium end-to-end suite.

This suite starts and owns its own throwaway backend + static-frontend
server pair so it never touches backend/data/prepai.db or interferes with
a developer's already-running dev servers. If ports 8000/5500 are already
taken, the session is aborted with a clear message instead of silently
reusing whatever is there.
"""
import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.wait import WebDriverWait

from urls import BACKEND_HOST, BACKEND_PORT, FRONTEND_HOST, FRONTEND_PORT, FRONTEND_URL

ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "prepai"
VENV_PYTHON = BACKEND_DIR / ".venv" / "Scripts" / "python.exe"


def _port_in_use(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _wait_for_port(host, port, up, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _port_in_use(host, port) == up:
            return True
        time.sleep(0.25)
    return False


class BackendProcess:
    """Owns the uvicorn subprocess so a single test (the offline-mode one)
    can stop and restart it against the same isolated database file."""

    def __init__(self, db_path):
        self.db_path = db_path
        self.proc = None

    def start(self):
        if self.proc is not None:
            return
        env = os.environ.copy()
        env["DATABASE_PATH"] = self.db_path
        for key in ("AI_QUESTIONS_ENABLED", "AI_EVALUATION_ENABLED", "OPENAI_API_KEY",
                    "MOCK_EVALUATION_ENABLED", "ENVIRONMENT"):
            env.pop(key, None)
        self.proc = subprocess.Popen(
            [str(VENV_PYTHON), "-m", "uvicorn", "main:app",
             "--host", BACKEND_HOST, "--port", str(BACKEND_PORT)],
            cwd=str(BACKEND_DIR),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not _wait_for_port(BACKEND_HOST, BACKEND_PORT, up=True, timeout=30):
            self.stop()
            raise RuntimeError("Selenium test backend did not start within 30s")

    def stop(self):
        if self.proc is None:
            return
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=10)
        self.proc = None
        _wait_for_port(BACKEND_HOST, BACKEND_PORT, up=False, timeout=10)


@pytest.fixture(scope="session")
def backend_server():
    if not VENV_PYTHON.exists():
        pytest.exit(f"Backend virtual environment not found at {VENV_PYTHON}", returncode=1)
    if _port_in_use(BACKEND_HOST, BACKEND_PORT):
        pytest.exit(
            f"Port {BACKEND_PORT} is already in use. Stop any already-running PrepAI "
            "backend first - this suite needs to start its own instance against an "
            "isolated test database.",
            returncode=1,
        )
    tmp_dir = tempfile.mkdtemp(prefix="prepai-selenium-db-")
    proc = BackendProcess(str(Path(tmp_dir) / "selenium-test.db"))
    proc.start()
    yield proc
    proc.stop()
    shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.fixture(scope="session")
def frontend_server():
    if _port_in_use(FRONTEND_HOST, FRONTEND_PORT):
        pytest.exit(
            f"Port {FRONTEND_PORT} is already in use. Stop any already-running static "
            "server (e.g. VS Code Live Server) first - this suite needs to serve "
            f"{FRONTEND_DIR} itself at exactly that origin (required by backend CORS).",
            returncode=1,
        )
    proc = subprocess.Popen(
        [str(VENV_PYTHON), "-m", "http.server", str(FRONTEND_PORT),
         "--bind", FRONTEND_HOST, "--directory", str(FRONTEND_DIR)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if not _wait_for_port(FRONTEND_HOST, FRONTEND_PORT, up=True, timeout=15):
        proc.terminate()
        pytest.exit("Static frontend server did not start within 15s", returncode=1)
    yield proc
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="module")
def driver(backend_server, frontend_server):
    options = Options()
    if os.environ.get("PREPAI_SELENIUM_HEADED") != "1":
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1366,900")
    options.add_argument("--disable-gpu")
    user_data_dir = tempfile.mkdtemp(prefix="prepai-chrome-profile-")
    options.add_argument(f"--user-data-dir={user_data_dir}")
    drv = webdriver.Chrome(options=options)
    drv.set_page_load_timeout(20)
    yield drv
    drv.quit()
    shutil.rmtree(user_data_dir, ignore_errors=True)


@pytest.fixture
def wait(driver):
    return WebDriverWait(driver, 10)


@pytest.fixture(scope="session")
def frontend_url():
    return FRONTEND_URL


def pytest_html_report_title(report):
    report.title = "PrepAI Selenium E2E Report"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    extras = getattr(report, "extras", [])
    if report.when == "call" and report.failed:
        driver_obj = item.funcargs.get("driver")
        if driver_obj is not None:
            try:
                import pytest_html

                shots_dir = ROOT / "reports" / "screenshots"
                shots_dir.mkdir(parents=True, exist_ok=True)
                shot_path = shots_dir / f"{item.name}.png"
                driver_obj.get_screenshot_as_file(str(shot_path))
                extras.append(pytest_html.extras.image(os.path.relpath(shot_path, ROOT / "reports")))
            except Exception:
                pass
    report.extras = extras
