"""Request and response shapes.

Pydantic checks incoming JSON before any business logic runs.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Recent turns are enough for a sales call and keep the Gemini request small.
MAX_HISTORY_MESSAGES = 20
MAX_MESSAGE_LENGTH = 4000


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=MAX_MESSAGE_LENGTH)

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message content cannot be empty.")
        return value


class ChatRequest(BaseModel):
    conversation_id: str | None = Field(default=None, max_length=80)
    message: str = Field(..., max_length=MAX_MESSAGE_LENGTH)
    conversation_history: list[ChatMessage] = Field(default_factory=list, max_length=MAX_HISTORY_MESSAGES)

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message cannot be empty.")
        return value


class LeadHints(BaseModel):
    customer_name: str | None = None
    company_name: str | None = None
    email: str | None = None
    vehicle_count: int | None = None
    business_problem: str | None = None
    interested_in_demo: bool | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    response: str
    mode: Literal["gemini", "demo"]
    knowledge_sections: list[str]
    lead_hints: LeadHints
    notice: str | None = None


class ScoreBreakdown(BaseModel):
    vehicle_count: int
    business_problem: int
    demo_interest: int
    contact_information: int


class LeadCreate(BaseModel):
    customer_name: str = Field(..., min_length=1, max_length=120)
    company_name: str = Field(..., min_length=1, max_length=160)
    email: str | None = Field(default=None, max_length=200)
    vehicle_count: int = Field(..., ge=0, le=1_000_000)
    business_problem: str = Field(default="", max_length=2000)
    interested_in_demo: bool = False
    call_summary: str | None = Field(default=None, max_length=8000)

    @field_validator("customer_name", "company_name")
    @classmethod
    def required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field is required.")
        return value

    @field_validator("business_problem")
    @classmethod
    def strip_problem(cls, value: str) -> str:
        return value.strip()

    @field_validator("email")
    @classmethod
    def clean_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if not EMAIL_RE.match(value):
            raise ValueError("Enter a valid email address or leave it blank.")
        return value

    @field_validator("call_summary")
    @classmethod
    def clean_summary(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class LeadResponse(BaseModel):
    id: int
    customer_name: str
    company_name: str
    email: str | None
    vehicle_count: int
    business_problem: str
    interested_in_demo: bool
    lead_score: int
    qualification_status: str
    call_summary: str | None
    next_action: str
    recommended_next_action: str
    score_breakdown: ScoreBreakdown
    created_at: str


class LeadListResponse(BaseModel):
    leads: list[LeadResponse]
    count: int


class SummarizeRequest(BaseModel):
    transcript: str = Field(..., min_length=1, max_length=20000)
    customer_name: str | None = Field(default=None, max_length=120)
    company_name: str | None = Field(default=None, max_length=160)
    email: str | None = Field(default=None, max_length=200)
    vehicle_count: int | None = Field(default=None, ge=0, le=1_000_000)
    business_problem: str | None = Field(default=None, max_length=2000)
    interested_in_demo: bool | None = None

    @field_validator("transcript")
    @classmethod
    def strip_transcript(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Transcript cannot be empty.")
        return value


class SummaryResponse(BaseModel):
    summary: str
    customer_requirements: str
    pain_points: str
    demo_interest: str
    next_action: str
    mode: Literal["gemini", "fallback"]
    lead_score: int | None = None
    qualification_status: str | None = None
    score_breakdown: ScoreBreakdown | None = None


class HealthResponse(BaseModel):
    status: str
    demo_mode: bool
    model: str | None
    database: str
    config_issue: str | None = None
