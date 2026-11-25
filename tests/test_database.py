from app.database import get_lead, init_db, insert_lead, list_leads, ping


def _sample(company="Northline Logistics"):
    return {
        "customer_name": "Priya Shah",
        "company_name": company,
        "email": "priya@northline.example",
        "vehicle_count": 35,
        "business_problem": "Manual route planning",
        "interested_in_demo": True,
        "lead_score": 100,
        "qualification_status": "Qualified",
        "call_summary": "Demo request recorded.",
        "next_action": "Schedule a product demonstration with the sales team.",
    }


def test_database_initializes_and_answers_ping(tmp_path):
    db_path = str(tmp_path / "nested" / "sales.db")
    init_db(db_path)
    assert ping(db_path) is True
    assert list_leads(db_path) == []


def test_save_and_retrieve_lead(tmp_path):
    db_path = str(tmp_path / "sales.db")
    init_db(db_path)
    saved = insert_lead(db_path, _sample())
    assert saved["id"] == 1
    assert saved["interested_in_demo"] is True
    assert get_lead(db_path, 1)["company_name"] == "Northline Logistics"
    assert get_lead(db_path, 99) is None
    assert len(list_leads(db_path)) == 1


def test_lead_persists_after_the_connection_closes(tmp_path):
    db_path = str(tmp_path / "sales.db")
    init_db(db_path)
    insert_lead(db_path, _sample())
    # A new connection sees the same file. That is the restart behaviour of SQLite.
    reopened = list_leads(db_path)
    assert reopened[0]["lead_score"] == 100
    assert reopened[0]["customer_name"] == "Priya Shah"


def test_sql_text_is_stored_as_data(tmp_path):
    db_path = str(tmp_path / "sales.db")
    init_db(db_path)
    hostile = "Acme'; DROP TABLE leads; --"
    insert_lead(db_path, _sample(company=hostile))
    leads = list_leads(db_path)
    assert len(leads) == 1
    assert leads[0]["company_name"] == hostile
