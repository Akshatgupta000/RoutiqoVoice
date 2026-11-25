"""SQLite storage for saved leads.

The conversation transcript is not stored. Only a lead the user explicitly
saves is written here. The Gemini API key is never written to the database.

Queries use ? placeholders. That keeps customer text inside a value, so it
cannot change the SQL command.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_name TEXT NOT NULL,
    company_name TEXT NOT NULL,
    email TEXT,
    vehicle_count INTEGER NOT NULL,
    business_problem TEXT,
    interested_in_demo INTEGER NOT NULL,
    lead_score INTEGER NOT NULL,
    qualification_status TEXT NOT NULL,
    call_summary TEXT,
    next_action TEXT,
    created_at TEXT NOT NULL
)
"""


def _ensure_parent(db_path: str) -> None:
    path = Path(db_path)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_connection(db_path: str) -> Iterator[sqlite3.Connection]:
    _ensure_parent(db_path)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db(db_path: str) -> None:
    """Create the leads table if it does not exist yet."""
    with get_connection(db_path) as connection:
        connection.execute(SCHEMA)


def ping(db_path: str) -> bool:
    try:
        with get_connection(db_path) as connection:
            connection.execute("SELECT 1")
        return True
    except sqlite3.Error:
        return False


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "customer_name": row["customer_name"],
        "company_name": row["company_name"],
        "email": row["email"],
        "vehicle_count": row["vehicle_count"],
        "business_problem": row["business_problem"] or "",
        "interested_in_demo": bool(row["interested_in_demo"]),
        "lead_score": row["lead_score"],
        "qualification_status": row["qualification_status"],
        "call_summary": row["call_summary"],
        "next_action": row["next_action"] or "",
        "created_at": row["created_at"],
    }


def insert_lead(db_path: str, lead: dict) -> dict:
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO leads (
                customer_name, company_name, email, vehicle_count,
                business_problem, interested_in_demo, lead_score,
                qualification_status, call_summary, next_action, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lead["customer_name"],
                lead["company_name"],
                lead.get("email"),
                lead["vehicle_count"],
                lead.get("business_problem") or "",
                1 if lead["interested_in_demo"] else 0,
                lead["lead_score"],
                lead["qualification_status"],
                lead.get("call_summary"),
                lead.get("next_action") or "",
                created_at,
            ),
        )
        lead_id = cursor.lastrowid
    saved = get_lead(db_path, int(lead_id))
    if saved is None:
        raise RuntimeError("Lead was inserted but could not be read back.")
    return saved


def list_leads(db_path: str) -> list[dict]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM leads ORDER BY id DESC"
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_lead(db_path: str, lead_id: int) -> dict | None:
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM leads WHERE id = ?",
            (lead_id,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_dict(row)
