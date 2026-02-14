"""E2E test fixtures using Playwright and a live uvicorn server."""

import os
import socket
import subprocess
import sys
import time
from contextlib import closing

import pytest
import requests


def find_free_port():
    """Find a free TCP port on localhost."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def server_port():
    """Get a free port for the test server."""
    return find_free_port()


@pytest.fixture(scope="session")
def base_url(server_port):
    """Base URL for the test server."""
    return f"http://localhost:{server_port}"


@pytest.fixture(scope="session", autouse=True)
def live_server(server_port, base_url):
    """Start a live uvicorn server for E2E tests.

    Uses an in-memory SQLite database so tests don't affect real data.
    """
    import os

    env = os.environ.copy()
    env["DATABASE_URL"] = "sqlite+aiosqlite:///./test_e2e.db"
    env["ENVIRONMENT"] = "development"
    env["GEMINI_API_KEY"] = ""  # No OCR in E2E tests
    env["LOG_LEVEL"] = "WARNING"  # Suppress app INFO logs
    env["RATE_LIMIT_PER_MINUTE"] = "9999"  # Effectively disable rate limiting for tests

    project_root = os.path.join(os.path.dirname(__file__), "..", "..")

    # Clean up any stale test DB
    db_path = os.path.join(project_root, "test_e2e.db")
    for suffix in ("", "-wal", "-shm"):
        p = db_path + suffix
        if os.path.exists(p):
            os.unlink(p)

    # Redirect server output to files to prevent pipe buffer deadlock.
    # When using subprocess.PIPE, the 64KB pipe buffer fills up with
    # log output and blocks the server process.
    log_out = os.path.join(project_root, "test_server.log")
    log_err = os.path.join(project_root, "test_server_err.log")
    stdout_f = open(log_out, "w")
    stderr_f = open(log_err, "w")

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            str(server_port),
            "--log-level",
            "warning",
        ],
        env=env,
        cwd=project_root,
        stdout=stdout_f,
        stderr=stderr_f,
    )

    # Wait for server to be ready
    max_wait = 10
    start = time.time()
    while time.time() - start < max_wait:
        try:
            r = requests.get(f"{base_url}/health", timeout=1)
            if r.status_code == 200:
                break
        except requests.ConnectionError:
            time.sleep(0.3)
    else:
        proc.kill()
        stdout_f.close()
        stderr_f.close()
        stdout_data = open(log_out).read() if os.path.exists(log_out) else ""
        stderr_data = open(log_err).read() if os.path.exists(log_err) else ""
        raise RuntimeError(
            f"Server failed to start within {max_wait}s.\n"
            f"stdout: {stdout_data}\nstderr: {stderr_data}"
        )

    yield base_url

    # Teardown: kill server and clean up DB + logs
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    stdout_f.close()
    stderr_f.close()

    project_root = os.path.join(os.path.dirname(__file__), "..", "..")
    for f in (
        "test_e2e.db",
        "test_e2e.db-wal",
        "test_e2e.db-shm",
        "test_server.log",
        "test_server_err.log",
    ):
        p = os.path.join(project_root, f)
        if os.path.exists(p):
            os.unlink(p)


@pytest.fixture
def api_url(base_url):
    """API base URL."""
    return f"{base_url}/api"


@pytest.fixture
def create_session_via_api(api_url):
    """Helper to create a session via API and return session data including host_token."""

    def _create(host_name="Test Host"):
        r = requests.post(f"{api_url}/sessions", json={"host_name": host_name})
        assert r.status_code == 201
        data = r.json()
        # Store host_token in the returned data
        return data

    return _create


@pytest.fixture
def add_items_via_api(api_url, create_session_via_api):
    """Helper to add items to a session via API. Requires host token."""
    # Store host tokens by session code for later use
    _tokens = {}

    def _add(code, items, host_token=None):
        # If no token provided, try to use a cached one
        if host_token is None:
            host_token = _tokens.get(code.upper())

        # If still no token, we need to create a session first to get one
        # This is a fallback - ideally the token should be passed
        if host_token is None:
            raise ValueError(
                f"No host token found for session {code}. "
                f"Either pass host_token parameter or use the create_session_via_api fixture first."
            )

        headers = {"X-Host-Token": host_token}
        results = []
        for item in items:
            r = requests.post(
                f"{api_url}/sessions/{code}/items", json=item, headers=headers
            )
            assert r.status_code == 201
            results.append(r.json())
        return results

    # Allow storing tokens for later use
    _add.set_token = lambda code, token: _tokens.update({code.upper(): token})

    return _add
