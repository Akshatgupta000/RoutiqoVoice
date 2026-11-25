import pytest
from fastapi.testclient import TestClient

from app.config import get_settings


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "sales.db"))
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GEMINI_MODEL", "")
    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def _lead_payload(**overrides):
    payload = {
        "customer_name": "Priya Shah",
        "company_name": "Northline Logistics",
        "email": "priya@northline.example",
        "vehicle_count": 35,
        "business_problem": "We struggle with manual route planning and late deliveries.",
        "interested_in_demo": True,
    }
    payload.update(overrides)
    return payload
