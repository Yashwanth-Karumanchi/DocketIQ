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
              c.incident_location,
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


def getDbActionPlanningContext(db: Session, currentUser: User, caseId: str) -> dict:
    caseContext = getCaseContext(db, caseId)

    taskRows = db.execute(
        text("""
            select id, title, description, status, priority, due_date, created_at
            from case_tasks
            where case_id = :case_id
            order by created_at desc
            limit 30
        """),
        {"case_id": caseId},
    ).mappings().all()

    connectedRows = db.execute(
        text("""
            select
              cr.relationship_type,
              cr.description,
              cr.strength,
              case
                when cr.source_case_id = :case_id then target_case.case_number
                else source_case.case_number
              end as connected_case_number,
              case
                when cr.source_case_id = :case_id then target_case.title
                else source_case.title
              end as connected_case_title,
              case
                when cr.source_case_id = :case_id then target_client.full_name
                else source_client.full_name
              end as connected_client_name
            from case_relationships cr
            join cases source_case on source_case.id = cr.source_case_id
            join clients source_client on source_client.id = source_case.client_id
            join cases target_case on target_case.id = cr.target_case_id
            join clients target_client on target_client.id = target_case.client_id
            where cr.source_case_id = :case_id
               or cr.target_case_id = :case_id
            order by cr.strength desc nulls last
            limit 20
        """),
        {"case_id": caseId},
    ).mappings().all()

    accessibleCaseRows = db.execute(
        text("""
            select c.case_number, c.title, cl.full_name as client_name
            from cases c
            join clients cl on cl.id = c.client_id
            join case_users cu on cu.case_id = c.id
            where cu.user_id = :user_id
              and c.id != :case_id
            order by c.created_at desc
            limit 50
        """),
        {
            "user_id": str(currentUser.id),
            "case_id": caseId,
        },
    ).mappings().all()

    return {
        "case": caseContext,
        "tasks": makeJsonSafe([dict(row) for row in taskRows]),
        "connectedCases": makeJsonSafe([dict(row) for row in connectedRows]),
        "accessibleCases": makeJsonSafe([dict(row) for row in accessibleCaseRows]),
    }


def inferActionType(message: str) -> str:
    lowered = message.lower()

    dbWords = [
        "add task",
        "create task",
        "update task",
        "change task",
        "mark task",
        "mark the",
        "delete task",
        "remove task",
        "close task",
        "complete task",
        "change priority",
        "update priority",
        "change status",
        "update status",
        "update summary",
        "change summary",
        "add timeline",
        "create timeline",
        "timeline event",
        "connect this case",
        "connect case",
        "connected to",
        "disconnect",
        "remove connection",
        "delete connection",
        "add communication suggestion",
        "create communication suggestion",
    ]

    if any(word in lowered for word in dbWords):
        return "db_manage"

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


def createDatabasePendingAction(db: Session, currentUser: User, caseId: str, userMessage: str):
    planningContext = getDbActionPlanningContext(db, currentUser, caseId)

    prompt = f"""
You are DocketIQ's database action planner.

The user wants to manage structured case data. You do NOT execute the action.
You only create a pending action that the user must confirm.

Allowed actionType values:
- db_create_task
- db_update_task
- db_delete_task
- db_update_case
- db_create_timeline_event
- db_connect_cases
- db_remove_case_connection
- db_create_communication_suggestion

Rules:
- Return ONLY valid JSON.
- Never return raw SQL.
- Never change users, permissions, audit logs, or authentication.
- Never hard-delete cases or clients.
- For task updates/deletes, use taskId if available from context.
- For connecting cases, use exact targetCaseNumber from accessibleCases.
- For removing case connections, use exact targetCaseNumber.
- If the user request is ambiguous, return needsClarification true.
- Keep preview short and clear.

JSON shape:
{{
  "needsClarification": false,
  "clarifyingQuestion": "",
  "actionType": "db_create_task",
  "preview": "Create a High priority task: Request police report.",
  "payload": {{
    "title": "Request police report",
    "description": "Ask client to provide police report.",
    "priority": "High",
    "status": "Open",
    "dueDate": null
  }}
}}

Payload examples:

db_create_task:
{{
  "title": "Request police report",
  "description": "Ask client to send police report.",
  "priority": "High",
  "status": "Open",
  "dueDate": "2026-07-10"
}}

db_update_task:
{{
  "taskId": "uuid if available",
  "targetTaskTitle": "treatment records",
  "status": "Complete",
  "priority": "High",
  "description": "optional"
}}

db_delete_task:
{{
  "taskId": "uuid if available",
  "targetTaskTitle": "duplicate task title"
}}

db_update_case:
{{
  "priority": "High",
  "status": "Attorney Review",
  "summary": "updated summary if requested",
  "insuranceCompany": "carrier if requested",
  "claimNumber": "claim if requested",
  "incidentLocation": "location if requested"
}}

db_create_timeline_event:
{{
  "eventDate": "2026-07-06",
  "eventType": "Follow Up",
  "title": "Insurance follow-up completed",
  "description": "Adjuster was contacted."
}}

db_connect_cases:
{{
  "targetCaseNumber": "CL-24245539",
  "relationshipType": "manual_user_connection",
  "description": "User stated these cases are connected.",
  "strength": 95
}}

db_remove_case_connection:
{{
  "targetCaseNumber": "CL-24245539"
}}

db_create_communication_suggestion:
{{
  "suggestionType": "client_follow_up",
  "priority": "High",
  "title": "Request missing police report",
  "reason": "Police report is needed before readiness review.",
  "draftPayload": {{
    "subject": "Missing police report for your case",
    "body": "Please send the police report when available."
  }}
}}

Current case and available data:
{json.dumps(planningContext, indent=2, default=str)}

User request:
{userMessage}
"""

    raw = generateText(prompt)
    data = parseJsonObject(raw)

    if data.get("needsClarification"):
        return {
            "needsClarification": True,
            "message": data.get("clarifyingQuestion") or "Please clarify the database update you want me to prepare.",
        }

    allowedActionTypes = {
        "db_create_task",
        "db_update_task",
        "db_delete_task",
        "db_update_case",
        "db_create_timeline_event",
        "db_connect_cases",
        "db_remove_case_connection",
        "db_create_communication_suggestion",
    }

    actionType = data.get("actionType")

    if actionType not in allowedActionTypes:
        return {
            "needsClarification": True,
            "message": "I can prepare safe case-data updates only for tasks, case fields, timeline events, case connections, and communication suggestions.",
        }

    actionPayload = data.get("payload") or {}

    if not isinstance(actionPayload, dict):
        return {
            "needsClarification": True,
            "message": "The action payload was not valid. Please rephrase the requested update.",
        }

    actionPayload.pop("rawSql", None)
    actionPayload["caseId"] = caseId

    preview = data.get("preview") or f"Prepare database action: {actionType}"

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
              :action_type,
              'pending',
              :preview,
              cast(:payload as jsonb)
            )
            returning id
        """),
        {
            "user_id": str(currentUser.id),
            "case_id": caseId,
            "action_type": actionType,
            "preview": preview,
            "payload": json.dumps(actionPayload),
        },
    ).mappings().first()

    return {
        "needsClarification": False,
        "pendingAction": {
            "id": str(row["id"]),
            "type": actionType,
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

    if actionType == "db_manage":
        return createDatabasePendingAction(db, currentUser, caseId, userMessage)

    if actionType == "email_send":
        return createEmailPendingAction(db, currentUser, caseId, userMessage)

    if actionType == "calendar_create":
        return createCalendarPendingAction(db, currentUser, caseId, userMessage)

    return {
        "needsClarification": True,
        "message": "I can help draft emails, create calendar events, or prepare safe case-data updates. Please clarify the action you want.",
    }