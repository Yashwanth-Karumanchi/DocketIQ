import json
from io import BytesIO
from datetime import datetime, date
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

from app.auth import getCurrentUser
from app.db import getDb
from app.models import User
from app.permissions import verifyCaseAccess
from app.llm import generateText, parseJsonObject


router = APIRouter(prefix="/api/legal-ops", tags=["legal-ops"])


def makeJsonSafe(value):
    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, dict):
        return {key: makeJsonSafe(item) for key, item in value.items()}

    if isinstance(value, list):
        return [makeJsonSafe(item) for item in value]

    return value


def getCaseOverview(db: Session, caseId: str) -> dict:
    row = db.execute(
        text("""
            select
              c.id,
              c.case_number,
              c.title,
              c.case_type,
              c.incident_date,
              c.status,
              c.priority,
              c.insurance_company,
              c.claim_number,
              c.summary,
              cl.full_name as client_name,
              cl.email as client_email,
              cl.phone as client_phone,
              cl.preferred_language
            from cases c
            join clients cl on cl.id = c.client_id
            where c.id = :case_id
            limit 1
        """),
        {"case_id": caseId},
    ).mappings().first()

    return makeJsonSafe(dict(row)) if row else {}


def getCaseDocumentContext(db: Session, caseId: str, limit: int = 40) -> str:
    rows = db.execute(
        text("""
            select
              d.file_name,
              dc.chunk_index,
              dc.content
            from document_chunks dc
            join documents d on d.id = dc.document_id
            where dc.case_id = :case_id
            order by d.created_at desc, dc.chunk_index asc
            limit :limit
        """),
        {
            "case_id": caseId,
            "limit": limit,
        },
    ).mappings().all()

    blocks = []

    for row in rows:
        blocks.append(
            f"""
File: {row["file_name"]}
Chunk: {row["chunk_index"]}
Content:
{row["content"]}
"""
        )

    return "\n\n".join(blocks)


def saveAudit(db: Session, currentUser: User, action: str, caseId: str, details: dict):
    db.execute(
        text("""
            insert into audit_logs (user_id, action, entity_type, entity_id, details)
            values (:user_id, :action, 'case', :case_id, cast(:details as jsonb))
        """),
        {
            "user_id": str(currentUser.id),
            "action": action,
            "case_id": caseId,
            "details": json.dumps(makeJsonSafe(details)),
        },
    )


@router.post("/cases/{caseId}/missing-items")
def generateMissingItems(
    caseId: str,
    db: Session = Depends(getDb),
    currentUser: User = Depends(getCurrentUser),
):
    verifyCaseAccess(db, currentUser, caseId)

    caseOverview = getCaseOverview(db, caseId)
    documentContext = getCaseDocumentContext(db, caseId)

    prompt = f"""
        You are DocketIQ's Senior Legal Operations Missing-Item Analyst.

        Create a professional missing-items report for a personal-injury case management team.

        The report must sound like a polished internal case-operations memo, not a casual chatbot answer.

        Analyze:
        - What documents are present
        - What documents are missing
        - Why each missing item matters operationally
        - Who should be contacted
        - What the next action should be
        - Priority level
        - Whether the missing item blocks attorney handoff

        Do not provide legal advice.
        Do not provide medical advice.
        Do not invent facts.
        Use only case overview and uploaded document context.

        Return only valid JSON.

        JSON shape:
        {{
        "reportTitle": "Missing Items Review",
        "executiveSummary": "professional paragraph",
        "readinessScore": 0,
        "handoffStatus": "Not Ready",
        "missingItems": [
            {{
            "title": "Police Report",
            "category": "Incident Documentation",
            "priority": "High",
            "blocksHandoff": true,
            "reason": "professional explanation",
            "recommendedOwner": "Case Manager",
            "recommendedAction": "specific action",
            "suggestedCommunication": "short email/call instruction"
            }}
        ],
        "presentItems": [
            {{
            "title": "Claim Number",
            "evidence": "MW-894201 appears in the case overview"
            }}
        ],
        "riskFlags": [
            {{
            "title": "Treatment records unavailable",
            "severity": "Medium",
            "explanation": "professional explanation"
            }}
        ],
        "nextOperationalSteps": [
            "step 1",
            "step 2"
        ]
        }}

        Case overview:
        {json.dumps(caseOverview, indent=2, default=str)}

        Uploaded document context:
        {documentContext}
        """

    raw = generateText(prompt)
    data = parseJsonObject(raw)

    for item in data.get("missingItems", []):
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
                "title": f"[AI Missing Item] {item.get('title', 'Missing item')}",
                "description": item.get("recommendedAction") or item.get("reason") or "",
                "priority": item.get("priority", "Medium"),
            },
        )

    saveAudit(
        db,
        currentUser,
        "missing_items_generated",
        caseId,
        {
            "missingCount": len(data.get("missingItems", [])),
            "riskFlagCount": len(data.get("riskFlags", [])),
        },
    )

    db.commit()

    return data


@router.post("/cases/{caseId}/timeline")
def generateTimeline(
    caseId: str,
    db: Session = Depends(getDb),
    currentUser: User = Depends(getCurrentUser),
):
    verifyCaseAccess(db, currentUser, caseId)

    caseOverview = getCaseOverview(db, caseId)
    documentContext = getCaseDocumentContext(db, caseId)

    prompt = f"""
You are DocketIQ's Senior Case Timeline Analyst.

Build a professional chronological case timeline for a personal-injury operations team.

The output must be clear enough for attorney handoff review.

Rules:
- Do not diagnose injuries.
- Do not provide medical advice.
- Do not infer dates that are not present.
- Use null if exact date is not available.
- Distinguish incident, treatment, insurance, documentation, communication, and task events.
- Return only valid JSON.

JSON shape:
{{
  "reportTitle": "Case Timeline Review",
  "executiveSummary": "professional paragraph",
  "timelineCompleteness": "Low/Medium/High",
  "events": [
    {{
      "eventDate": "2026-06-10",
      "eventType": "Incident",
      "title": "Rear-end collision reported",
      "description": "professional description",
      "source": "case overview or file name",
      "confidence": "High"
    }}
  ],
  "timelineGaps": [
    {{
      "gap": "No treatment visit dates available",
      "impact": "Limits ability to verify chronology of care",
      "recommendedAction": "Request treatment records and billing ledger"
    }}
  ],
  "nextOperationalSteps": [
    "step 1",
    "step 2"
  ]
}}

Case overview:
{json.dumps(caseOverview, indent=2, default=str)}

Uploaded document context:
{documentContext}
"""

    raw = generateText(prompt)
    data = parseJsonObject(raw)

    for event in data.get("events", []):
        eventDate = event.get("eventDate")

        if not eventDate:
            continue

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
                  :source
                )
            """),
            {
                "case_id": caseId,
                "event_date": eventDate,
                "event_type": event.get("eventType", "Case Event"),
                "title": event.get("title", "Timeline event"),
                "description": event.get("description", ""),
                "source": event.get("source", "DocketIQ"),
            },
        )

    saveAudit(
        db,
        currentUser,
        "timeline_generated",
        caseId,
        {
            "eventCount": len(data.get("events", [])),
            "gapCount": len(data.get("gaps", [])),
        },
    )

    db.commit()

    return data


def buildPdf(caseOverview: dict, reportData: dict) -> BytesIO:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("DocketIQ Attorney Handoff Report", styles["Title"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Case Overview", styles["Heading2"]))

    overviewRows = [
        ["Case Number", caseOverview.get("case_number", "")],
        ["Client", caseOverview.get("client_name", "")],
        ["Case Type", caseOverview.get("case_type", "")],
        ["Status", caseOverview.get("status", "")],
        ["Priority", caseOverview.get("priority", "")],
        ["Insurance", caseOverview.get("insurance_company", "") or "Not added"],
        ["Claim Number", caseOverview.get("claim_number", "") or "Not added"],
    ]

    table = Table(overviewRows, colWidths=[130, 360])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3eee7")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#1f2933")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d8cabb")),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(table)
    story.append(Spacer(1, 16))

    sections = [
        ("Executive Summary", reportData.get("executiveSummary", "")),
        ("Incident Summary", reportData.get("incidentSummary", "")),
        ("Treatment Summary", reportData.get("treatmentSummary", "")),
        ("Insurance Summary", reportData.get("insuranceSummary", "")),
        ("Missing Items", reportData.get("missingItems", [])),
        ("Risk Flags", reportData.get("riskFlags", [])),
        ("Recommended Next Operational Steps", reportData.get("nextSteps", [])),
        ("Limitations", reportData.get("limitations", "")),
    ]

    for title, content in sections:
        story.append(Paragraph(title, styles["Heading2"]))

        if isinstance(content, list):
            if not content:
                story.append(Paragraph("None identified.", styles["BodyText"]))
            else:
                for item in content:
                    story.append(Paragraph(f"• {item}", styles["BodyText"]))
        else:
            story.append(Paragraph(str(content or "Not available."), styles["BodyText"]))

        story.append(Spacer(1, 10))

    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "Generated by DocketIQ. This report is for legal operations support only and does not provide legal or medical advice.",
        styles["Italic"],
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer


@router.get("/cases/{caseId}/handoff-report")
def generateHandoffReport(
    caseId: str,
    db: Session = Depends(getDb),
    currentUser: User = Depends(getCurrentUser),
):
    verifyCaseAccess(db, currentUser, caseId)

    caseOverview = getCaseOverview(db, caseId)
    documentContext = getCaseDocumentContext(db, caseId)

    missingRows = db.execute(
        text("""
            select title, description, priority, status
            from case_tasks
            where case_id = :case_id
            order by created_at desc
            limit 20
        """),
        {"case_id": caseId},
    ).mappings().all()

    timelineRows = db.execute(
        text("""
            select event_date, event_type, title, description, source
            from case_timeline_events
            where case_id = :case_id
            order by event_date asc
            limit 30
        """),
        {"case_id": caseId},
    ).mappings().all()

    prompt = f"""
You are DocketIQ's Attorney Handoff Report Agent.

Generate a concise attorney-ready operational case handoff report.

Rules:
- Do not provide legal advice.
- Do not provide medical advice or diagnosis.
- Do not recommend whether to sue, settle, or accept liability.
- Use only the supplied case overview, tasks, timeline, and document context.
- Return only valid JSON.

JSON shape:
{{
  "executiveSummary": "short summary",
  "incidentSummary": "what happened according to case docs",
  "treatmentSummary": "treatment-related operational summary",
  "insuranceSummary": "insurance and claim info",
  "missingItems": ["item 1", "item 2"],
  "riskFlags": ["flag 1"],
  "nextSteps": ["step 1", "step 2"],
  "limitations": "what is unknown or not available in the uploaded file"
}}

Case overview:
{json.dumps(caseOverview, indent=2, default=str)}

Existing missing item tasks:
{json.dumps(makeJsonSafe([dict(row) for row in missingRows]), indent=2, default=str)}

Existing timeline:
{json.dumps(makeJsonSafe([dict(row) for row in timelineRows]), indent=2, default=str)}

Uploaded document context:
{documentContext}
"""

    raw = generateText(prompt)
    reportData = parseJsonObject(raw)

    db.execute(
        text("""
            insert into report_logs (
              user_id,
              case_id,
              report_type,
              title,
              summary
            )
            values (
              :user_id,
              :case_id,
              'attorney_handoff',
              :title,
              cast(:summary as jsonb)
            )
        """),
        {
            "user_id": str(currentUser.id),
            "case_id": caseId,
            "title": f"Attorney Handoff Report - {caseOverview.get('case_number')}",
            "summary": json.dumps(makeJsonSafe(reportData)),
        },
    )

    saveAudit(
        db,
        currentUser,
        "handoff_report_generated",
        caseId,
        {
            "caseNumber": caseOverview.get("case_number"),
            "clientName": caseOverview.get("client_name"),
        },
    )

    db.commit()

    pdfBuffer = buildPdf(caseOverview, reportData)
    fileName = f"docketiq_handoff_{caseOverview.get('case_number', 'case')}.pdf"

    return StreamingResponse(
        pdfBuffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{fileName}"'
        },
    )