from app.config import get_settings
from app.knowledge_base import build_knowledge_context, retrieve
from tests.conftest import _lead_payload


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["demo_mode"] is True
    assert body["database"] == "ok"
    assert "gemini_api_key" not in body
    dumped = str(body).lower()
    assert "your_api_key_here" not in dumped


def test_dashboard_and_static_files(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "AI Sales Agent" in page.text
    assert "Save lead and summarize" in page.text
    assert client.get("/static/style.css").status_code == 200
    assert client.get("/static/script.js").status_code == 200


def test_chat_demo_mode_remembers_earlier_turns(client):
    first = client.post("/api/chat", json={
        "message": "Hi, I am Priya Shah from Northline Logistics.",
        "conversation_history": [],
    })
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["mode"] == "demo"
    assert first_body["lead_hints"]["company_name"] == "Northline Logistics"
    assert "Gemini" not in first_body["response"]
    assert "What company" not in first_body["response"]

    second = client.post("/api/chat", json={
        "conversation_id": first_body["conversation_id"],
        "message": "We have 35 vehicles.",
        "conversation_history": [
            {"role": "user", "content": "Hi, I am Priya Shah from Northline Logistics."},
            {"role": "assistant", "content": first_body["response"]},
        ],
    })
    assert second.status_code == 200
    body = second.json()
    assert body["conversation_id"] == first_body["conversation_id"]
    assert body["lead_hints"]["vehicle_count"] == 35
    assert body["lead_hints"]["customer_name"] == "Priya Shah"
    assert "What company" not in body["response"]


def test_chat_rejects_an_empty_message(client):
    response = client.post("/api/chat", json={"message": "   "})
    assert response.status_code == 422


def test_unknown_product_question_is_not_invented(client):
    response = client.post("/api/chat", json={
        "message": "Do you integrate with SAP?",
    })
    assert response.status_code == 200
    text = response.json()["response"].lower()
    assert "sales team" in text
    assert "sap" not in text or "do not" in text or "does not" in text or "product notes" in text


def test_create_lead_scores_on_the_server(client):
    response = client.post("/api/leads", json=_lead_payload(lead_score=1, qualification_status="Not Qualified"))
    assert response.status_code == 200
    body = response.json()
    assert body["lead_score"] == 100
    assert body["qualification_status"] == "Qualified"
    assert body["recommended_next_action"] == "Schedule a product demonstration with the sales team."
    assert body["interested_in_demo"] is True
    assert body["score_breakdown"]["vehicle_count"] == 30

    listed = client.get("/api/leads")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1

    fetched = client.get(f"/api/leads/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["company_name"] == "Northline Logistics"


def test_lead_persists_across_restart(client, tmp_path, monkeypatch):
    created = client.post("/api/leads", json=_lead_payload())
    assert created.status_code == 200
    lead_id = created.json()["id"]
    database_path = str(tmp_path / "sales.db")
    monkeypatch.setenv("DATABASE_PATH", database_path)
    get_settings.cache_clear()
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as restarted:
        fetched = restarted.get(f"/api/leads/{lead_id}")
        assert fetched.status_code == 200
        assert fetched.json()["email"] == "priya@northline.example"


def test_missing_lead_returns_404(client):
    response = client.get("/api/leads/999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Lead not found."


def test_lead_validation(client):
    missing = client.post("/api/leads", json={"customer_name": "Priya"})
    assert missing.status_code == 422
    negative = client.post("/api/leads", json=_lead_payload(vehicle_count=-1))
    assert negative.status_code == 422
    bad_email = client.post("/api/leads", json=_lead_payload(email="not-an-email"))
    assert bad_email.status_code == 422


def test_summary_fallback_without_gemini(client):
    response = client.post("/api/summarize", json={
        "transcript": "Customer: We have 35 vehicles and want a demo.",
        "customer_name": "Priya Shah",
        "company_name": "Northline Logistics",
        "email": "priya@northline.example",
        "vehicle_count": 35,
        "business_problem": "Manual route planning",
        "interested_in_demo": True,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "fallback"
    assert body["demo_interest"] == "Demo requested"
    assert body["lead_score"] == 100
    assert "Schedule a product demonstration" in body["next_action"]
    assert "Priya Shah" in body["summary"]


def test_knowledge_retrieval_finds_routing_and_not_embeddings():
    matches = retrieve("How does Routiqo optimize routes?")
    titles = [section["title"] for section in matches]
    assert any("route" in title.lower() or "routing" in title.lower() for title in titles)
    context, returned_titles = build_knowledge_context("What is the price?")
    assert "price" in context.lower() or "pricing" in context.lower()
    assert returned_titles
    assert "embedding" not in context.lower()
