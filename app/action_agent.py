import json
from datetime import datetime, timezone, date
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.llm import generateText, parseJsonObject
from app.models import User

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

def getCaseContext(db: Session, caseId: str) -> dict:
    row = db.execute(
        text("""
            select
              c.id,
              c.case_number,
              c.title,
              c.status,
              c.priority,
              c.summary,
              c.insurance_company,
              c.claim_number,
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

def inferActionType(message: str) -> str:
    lowered = message.lower()

    calendarWords = ["schedule", "calendar", "meeting", "consultation", "appointment", "invite"]
    emailWords = ["email", "mail", "send", "follow up", "follow-up"]

    if any(word in lowered for word in calendarWords):
        return "calendar_create"

    if any(word in lowered for word in emailWords):
        return "email_send"

    return "unknown"

def createEmailPendingAction(db: Session, currentUser: User, caseId: str, userMessage: str):
    caseContext = getCaseContext(db, caseId)

    if not caseContext.get("client_email"):
        return {
            "needsClarification": True,
            "message": "This case does not have a client email. Please add an email before sending.",
        }

    prompt = f"""
You are DocketIQ's email action planner.

Create a safe operational email draft for a personal-injury legal operations case.

Rules:
- Do not provide legal advice.
- Do not provide medical advice.
- Do not exaggerate injuries.
- Do not invent facts beyond the case context.
- Use a professional, concise tone.
- The email should be from the case team.
- The recipient should usually be the client unless the user names someone else.
- Return ONLY valid JSON.

JSON shape:
{{
  "toEmail": "recipient@example.com",
  "subject": "email subject",
  "body": "email body"
}}

Case context:
{json.dumps(caseContext, indent=2, default=str)}

User request:
{userMessage}
"""

    raw = generateText(prompt)
    data = parseJsonObject(raw)

    toEmail = data.get("toEmail") or caseContext.get("client_email")
    subject = data.get("subject") or f"Follow-up for {caseContext.get('case_number')}"
    body = data.get("body") or ""

    preview = f"""Email Draft

To: {toEmail}
Subject: {subject}

{body}
"""

    row = db.execute(
        text("""
            insert into pending_agent_actions (
              user_id,
              case_id,
              action_type,
              status,
              preview,
              payload
            )
            values (
              :user_id,
              :case_id,
              'email_send',
              'pending',
              :preview,
              cast(:payload as jsonb)
            )
            returning id
        """),
        {
            "user_id": str(currentUser.id),
            "case_id": caseId,
            "preview": preview,
            "payload": json.dumps({
                "toEmail": toEmail,
                "subject": subject,
                "body": body,
            }),
        },
    ).mappings().first()

    return {
        "needsClarification": False,
        "pendingAction": {
            "id": str(row["id"]),
            "type": "email_send",
            "preview": preview,
        },
    }

def createCalendarPendingAction(db: Session, currentUser: User, caseId: str, userMessage: str):
    caseContext = getCaseContext(db, caseId)
    now = datetime.now(timezone.utc).isoformat()

    prompt = f"""
You are DocketIQ's calendar action planner.

Create a safe calendar event payload for a personal-injury legal operations case.

Rules:
- Do not provide legal advice.
- Do not provide medical advice.
- If the user does not provide enough date/time information, return needsClarification true.
- Default timezone is America/Denver.
- Default duration is 30 minutes unless the user asks otherwise.
- Use the client email as attendee only if the request implies the client should be invited.
- Return ONLY valid JSON.

JSON shape:
{{
  "needsClarification": false,
  "clarifyingQuestion": "",
  "title": "event title",
  "description": "event description",
  "startTime": "2026-06-16T15:00:00",
  "endTime": "2026-06-16T15:30:00",
  "timeZone": "America/Denver",
  "attendees": ["client@example.com"]
}}

Current UTC time:
{now}

Case context:
{json.dumps(caseContext, indent=2, default=str)}

User request:
{userMessage}
"""

    raw = generateText(prompt)
    data = parseJsonObject(raw)

    if data.get("needsClarification"):
        return {
            "needsClarification": True,
            "message": data.get("clarifyingQuestion") or "Please provide the date, time, and duration for the calendar event.",
        }

    title = data.get("title") or f"Case follow-up: {caseContext.get('client_name')}"
    description = data.get("description") or f"Follow-up for case {caseContext.get('case_number')}"
    startTime = data.get("startTime")
    endTime = data.get("endTime")
    timeZone = data.get("timeZone") or "America/Denver"
    attendees = data.get("attendees") or []

    if not startTime or not endTime:
        return {
            "needsClarification": True,
            "message": "Please provide a clear start time and end time for the calendar event.",
        }

    preview = f"""Calendar Event Draft

Title: {title}
Start: {startTime} {timeZone}
End: {endTime} {timeZone}
Attendees: {", ".join(attendees) if attendees else "No external attendees"}

Description:
{description}
"""

    row = db.execute(
        text("""
            insert into pending_agent_actions (
              user_id,
              case_id,
              action_type,
              status,
              preview,
              payload
            )
            values (
              :user_id,
              :case_id,
              'calendar_create',
              'pending',
              :preview,
              cast(:payload as jsonb)
            )
            returning id
        """),
        {
            "user_id": str(currentUser.id),
            "case_id": caseId,
            "preview": preview,
            "payload": json.dumps({
                "title": title,
                "description": description,
                "startTime": startTime,
                "endTime": endTime,
                "timeZone": timeZone,
                "attendees": attendees,
            }),
        },
    ).mappings().first()

    return {
        "needsClarification": False,
        "pendingAction": {
            "id": str(row["id"]),
            "type": "calendar_create",
            "preview": preview,
        },
    }

def createPendingActionFromMessage(
    db: Session,
    currentUser: User,
    caseId: str,
    userMessage: str,
):
    actionType = inferActionType(userMessage)

    if actionType == "email_send":
        return createEmailPendingAction(db, currentUser, caseId, userMessage)

    if actionType == "calendar_create":
        return createCalendarPendingAction(db, currentUser, caseId, userMessage)

    return {
        "needsClarification": True,
        "message": "I can help draft emails or create calendar events. Please clarify the action you want.",
    }