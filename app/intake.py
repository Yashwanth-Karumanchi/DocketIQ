import json
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.auth import getCurrentUser
from app.db import getDb
from app.models import User
from app.llm import generateText, parseJsonObject

router = APIRouter(prefix="/api/intake", tags=["intake"])


class IntakeCreateRequest(BaseModel):
    clientName: str
    clientEmail: Optional[EmailStr] = None
    clientPhone: Optional[str] = None
    preferredLanguage: Optional[str] = "English"

    caseType: Optional[str] = "Personal Injury"
    incidentDate: Optional[date] = None
    incidentType: Optional[str] = None
    incidentLocation: Optional[str] = None
    insuranceCompany: Optional[str] = None
    claimNumber: Optional[str] = None

    priority: Optional[str] = "Medium"
    intakeNotes: str


def nextCaseNumber(db: Session) -> str:
    row = db.execute(
        text("""
            select case_number
            from cases
            where case_number like 'CL-%'
            order by case_number desc
            limit 1
        """)
    ).mappings().first()

    if not row:
        return "CL-24245501"

    current = row["case_number"].replace("CL-", "")

    try:
        nextNumber = int(current) + 1
    except Exception:
        nextNumber = 24245501

    return f"CL-{nextNumber}"


def buildIntakeAgentResult(payload: IntakeCreateRequest) -> dict:
    prompt = f"""
You are DocketIQ's Intake Agent for a legal operations case-management platform.

Create a professional operational intake plan.

Rules:
- Do not provide legal advice.
- Do not provide medical advice.
- Do not infer liability.
- Use only the provided intake information.
- If something is missing, create a missing-item task.
- Return only valid JSON.

JSON shape:
{{
  "caseTitle": "Client Name - Incident Type",
  "caseSummary": "professional operational summary",
  "priority": "Low / Medium / High",
  "timelineEvents": [
    {{
      "eventType": "Intake",
      "title": "Initial intake completed",
      "description": "professional description"
    }}
  ],
  "tasks": [
    {{
      "title": "[AI Missing Item] Police report",
      "description": "why this is needed operationally",
      "priority": "High"
    }}
  ],
  "recommendedNextSteps": [
    "step 1",
    "step 2"
  ]
}}

Intake data:
{payload.model_dump_json(indent=2)}
"""

    raw = generateText(prompt)
    data = parseJsonObject(raw)

    if not data.get("caseTitle"):
        data["caseTitle"] = f"{payload.clientName} - {payload.incidentType or 'New Intake'}"

    if not data.get("caseSummary"):
        data["caseSummary"] = payload.intakeNotes

    if not data.get("priority"):
        data["priority"] = payload.priority or "Medium"

    if not data.get("tasks"):
        data["tasks"] = []

    if not data.get("timelineEvents"):
        data["timelineEvents"] = [
            {
                "eventType": "Intake",
                "title": "Initial intake completed",
                "description": "Initial case intake was created from web intake form.",
            }
        ]

    return data


@router.post("/cases")
def createCaseFromIntake(
    payload: IntakeCreateRequest,
    db: Session = Depends(getDb),
    currentUser: User = Depends(getCurrentUser),
):
    if not payload.clientName.strip():
        raise HTTPException(status_code=422, detail="Client name is required.")

    if not payload.intakeNotes.strip():
        raise HTTPException(status_code=422, detail="Intake notes are required.")

    agentResult = buildIntakeAgentResult(payload)
    caseNumber = nextCaseNumber(db)

    existingClient = None

    if payload.clientEmail:
        existingClient = db.execute(
            text("""
                select id
                from clients
                where lower(email) = lower(:email)
                limit 1
            """),
            {"email": str(payload.clientEmail)},
        ).mappings().first()

    if existingClient:
        clientId = str(existingClient["id"])

        db.execute(
            text("""
                update clients
                set
                  full_name = :full_name,
                  phone = coalesce(:phone, phone),
                  preferred_language = coalesce(:preferred_language, preferred_language)
                where id = :client_id
            """),
            {
                "client_id": clientId,
                "full_name": payload.clientName,
                "phone": payload.clientPhone,
                "preferred_language": payload.preferredLanguage,
            },
        )
    else:
        clientRow = db.execute(
            text("""
                insert into clients (
                  full_name,
                  email,
                  phone,
                  preferred_language
                )
                values (
                  :full_name,
                  :email,
                  :phone,
                  :preferred_language
                )
                returning id
            """),
            {
                "full_name": payload.clientName,
                "email": str(payload.clientEmail) if payload.clientEmail else None,
                "phone": payload.clientPhone,
                "preferred_language": payload.preferredLanguage or "English",
            },
        ).mappings().first()

        clientId = str(clientRow["id"])

    caseRow = db.execute(
        text("""
            insert into cases (
              client_id,
              case_number,
              title,
              case_type,
              incident_date,
              status,
              priority,
              insurance_company,
              claim_number,
              summary
            )
            values (
              :client_id,
              :case_number,
              :title,
              :case_type,
              :incident_date,
              'Intake',
              :priority,
              :insurance_company,
              :claim_number,
              :summary
            )
            returning id
        """),
        {
            "client_id": clientId,
            "case_number": caseNumber,
            "title": agentResult.get("caseTitle"),
            "case_type": payload.caseType or "Personal Injury",
            "incident_date": payload.incidentDate,
            "priority": agentResult.get("priority", payload.priority or "Medium"),
            "insurance_company": payload.insuranceCompany,
            "claim_number": payload.claimNumber,
            "summary": agentResult.get("caseSummary"),
        },
    ).mappings().first()

    caseId = str(caseRow["id"])

    db.execute(
        text("""
            insert into case_users (
              case_id,
              user_id,
              access_level
            )
            values (
              :case_id,
              :user_id,
              'manager'
            )
            on conflict do nothing
        """),
        {
            "case_id": caseId,
            "user_id": str(currentUser.id),
        },
    )

    for event in agentResult.get("timelineEvents", []):
        db.execute(
            text("""
                insert into case_timeline_events (
                  case_id,
                  event_date,
                  event_type,
                  title,
                  description,
                  source
                )
                values (
                  :case_id,
                  :event_date,
                  :event_type,
                  :title,
                  :description,
                  'Intake Agent'
                )
            """),
            {
                "case_id": caseId,
                "event_date": payload.incidentDate,
                "event_type": event.get("eventType", "Intake"),
                "title": event.get("title", "Initial intake completed"),
                "description": event.get("description", ""),
            },
        )

    for task in agentResult.get("tasks", []):
        db.execute(
            text("""
                insert into case_tasks (
                  case_id,
                  title,
                  description,
                  status,
                  priority
                )
                values (
                  :case_id,
                  :title,
                  :description,
                  'Open',
                  :priority
                )
            """),
            {
                "case_id": caseId,
                "title": task.get("title", "[AI Intake Task] Review intake"),
                "description": task.get("description", ""),
                "priority": task.get("priority", "Medium"),
            },
        )

    db.execute(
        text("""
            insert into agent_runs (
              user_id,
              case_id,
              agent_name,
              status,
              result_summary,
              result_payload
            )
            values (
              :user_id,
              :case_id,
              'intake_agent',
              'success',
              :result_summary,
              cast(:result_payload as jsonb)
            )
        """),
        {
            "user_id": str(currentUser.id),
            "case_id": caseId,
            "result_summary": agentResult.get("caseSummary", ""),
            "result_payload": json.dumps(agentResult),
        },
    )

    db.execute(
        text("""
            insert into audit_logs (
              user_id,
              action,
              entity_type,
              entity_id,
              details
            )
            values (
              :user_id,
              'case_created_from_intake',
              'case',
              :case_id,
              cast(:details as jsonb)
            )
        """),
        {
            "user_id": str(currentUser.id),
            "case_id": caseId,
            "details": json.dumps({
                "caseNumber": caseNumber,
                "clientName": payload.clientName,
                "source": "web_intake_agent",
            }),
        },
    )

    db.commit()

    return {
        "message": "Case created from intake.",
        "caseId": caseId,
        "caseNumber": caseNumber,
        "agentResult": agentResult,
    }