import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
_tmp = tempfile.mkdtemp()
os.environ["SQLITE_PATH"] = os.path.join(_tmp, "test.db")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("GEMINI_API_KEY", None)
os.environ["JWT_SECRET"] = "test-secret-for-pytest-only-0123456789abcdef"


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from backend.app.main import app
    with TestClient(app) as c:
        yield c


def login(client, email, password="Demo@2026"):
    r = client.post("/auth/token", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def ayesha(client):
    return login(client, "ayesha@northwind.example")


@pytest.fixture(scope="session")
def sara(client):
    return login(client, "sara@northwind.example")
