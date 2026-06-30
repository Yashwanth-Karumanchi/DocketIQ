from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
import json

from app.db import getDb
from app.auth import getCurrentUser
from app.models import User

router = APIRouter(prefix="/api/cases", tags=["cases"])

class CaseCreate(BaseModel):
    clientName: str
    clientEmail: Optional[str] = None
    clientPhone: Optional[str] = None
    preferredLanguage: str = "English"
    title: str
    caseNumber: str
    incidentDate: Optional[str] = None
    priority: str = "Medium"
    insuranceCompany: Optional[str] = None
    claimNumber: Optional[str] = None
    summary: Optional[str] = None

@router.get("")
def listCases(
    db: Session = Depends(getDb),
    currentUser: User = Depends(getCurrentUser),
):
    rows = db.execute(
        text("""
            select
              c.id,
              c.case_number,
              c.title,
              c.status,
              c.priority,
              c.incident_date,
              c.insurance_company,
              c.claim_number,
              c.summary,
              cl.full_name as client_name,
              cl.email as client_email,
              cl.phone as client_phone
            from cases c
            join clients cl on cl.id = c.client_id
            join case_users cu on cu.case_id = c.id
            where cu.user_id = :user_id
            order by c.created_at desc
        """),
        {"user_id": str(currentUser.id)},
    ).mappings().all()

    return {"cases": [dict(row) for row in rows]}

@router.post("")
def createCase(
    payload: CaseCreate,
    db: Session = Depends(getDb),
    currentUser: User = Depends(getCurrentUser),
):
    existing = db.execute(
        text("select id from cases where case_number = :case_number"),
        {"case_number": payload.caseNumber},
    ).first()

    if existing:
        raise HTTPException(status_code=409, detail="Case number already exists")

    client = db.execute(
        text("""
            insert into clients (full_name, email, phone, preferred_language)
            values (:full_name, :email, :phone, :preferred_language)
            returning id
        """),
        {
            "full_name": payload.clientName,
            "email": payload.clientEmail,
            "phone": payload.clientPhone,
            "preferred_language": payload.preferredLanguage,
        },
    ).mappings().first()

    case = db.execute(
        text("""
            insert into cases (
              client_id,
              case_number,
              title,
              incident_date,
              priority,
              insurance_company,
              claim_number,
              summary
            )
            values (
              :client_id,
              :case_number,
              :title,
              :incident_date,
              :priority,
              :insurance_company,
              :claim_number,
              :summary
            )
            returning id
        """),
        {
            "client_id": str(client["id"]),
            "case_number": payload.caseNumber,
            "title": payload.title,
            "incident_date": payload.incidentDate,
            "priority": payload.priority,
            "insurance_company": payload.insuranceCompany,
            "claim_number": payload.claimNumber,
            "summary": payload.summary,
        },
    ).mappings().first()

    db.execute(
        text("""
            insert into case_users (case_id, user_id, access_level)
            values (:case_id, :user_id, 'manager')
        """),
        {
            "case_id": str(case["id"]),
            "user_id": str(currentUser.id),
        },
    )

    db.execute(
        text("""
            insert into audit_logs (user_id, action, entity_type, entity_id, details)
            values (:user_id, 'case_created', 'case', :case_id, :details)
        """),
        {
            "user_id": str(currentUser.id),
            "case_id": str(case["id"]),
            "details": json.dumps({
                "caseNumber": payload.caseNumber,
                "clientName": payload.clientName,
            }),
        },
    )

    db.commit()

    return {"id": str(case["id"]), "message": "Case created"}