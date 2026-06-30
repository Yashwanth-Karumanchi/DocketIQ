import json
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.auth import getCurrentUser
from app.db import getDb
from app.models import User
from app.permissions import verifyCaseAccess
from app.action_agent import getCaseContext
from app.llm import generateText, parseJsonObject

router = APIRouter(prefix="/api/autopilot", tags=["autopilot"])


@router.post("/cases/{caseId}/refresh")
def refreshAutopilot(
    caseId: str,
    db: Session = Depends(getDb),
    currentUser: User = Depends(getCurrentUser),
):
    verifyCaseAccess(db, currentUser, caseId)

    caseContext = getCaseContext(db, caseId)

    taskRows = db.execute(
        text("""
            select title, description, priority, status
            from case_tasks
            where case_id = :case_id
              and status = 'Open'
            order by created_at desc
            limit 20
        """),
        {"case_id": caseId},
    ).mappings().all()

    pendingRows = db.execute(
        text("""
            select action_type, status, preview
            from pending_agent_actions
            where case_id = :case_id
              and status = 'pending'
            order by created_at desc
            limit 10
        """),
        {"case_id": caseId},
    ).mappings().all()

    prompt = f"""
You are DocketIQ's Communication Autopilot Agent.

Create useful communication suggestions for a legal operations case manager.

Your job:
- Prepare draft emails that the user can review and send
- Ask for missing documents
- Schedule calls when needed
- Follow up on unresolved operational tasks
- Avoid duplicate drafts that already exist
- Do not send anything automatically
- Do not provide legal advice
- Do not provide medical advice
- Use professional tone

Return only valid JSON.

JSON shape:
{{
  "summary": "professional summary",
  "suggestions": [
    {{
      "suggestionType": "email_missing_docs",
      "priority": "High",
      "title": "Request police report and treatment records from client",
      "reason": "why this draft helps",
      "toEmail": "client@example.com",
      "subject": "Documents needed for your case file",
      "body": "professional email body"
    }}
  ]
}}

Case context:
{json.dumps(caseContext, indent=2, default=str)}

Open tasks:
{json.dumps([dict(row) for row in taskRows], indent=2, default=str)}

Existing pending actions:
{json.dumps([dict(row) for row in pendingRows], indent=2, default=str)}
"""

    raw = generateText(prompt)
    data = parseJsonObject(raw)

    created = []

    for suggestion in data.get("suggestions", []):
        row = db.execute(
            text("""
                insert into communication_suggestions (
                  user_id,
                  case_id,
                  suggestion_type,
                  priority,
                  title,
                  reason,
                  draft_payload,
                  status
                )
                values (
                  :user_id,
                  :case_id,
                  :suggestion_type,
                  :priority,
                  :title,
                  :reason,
                  cast(:draft_payload as jsonb),
                  'suggested'
                )
                returning id
            """),
            {
                "user_id": str(currentUser.id),
                "case_id": caseId,
                "suggestion_type": suggestion.get("suggestionType", "email"),
                "priority": suggestion.get("priority", "Medium"),
                "title": suggestion.get("title", "Suggested communication"),
                "reason": suggestion.get("reason", ""),
                "draft_payload": json.dumps({
                    "toEmail": suggestion.get("toEmail"),
                    "subject": suggestion.get("subject"),
                    "body": suggestion.get("body"),
                }),
            },
        ).mappings().first()

        created.append(str(row["id"]))

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
              'communication_autopilot',
              'success',
              :result_summary,
              cast(:result_payload as jsonb)
            )
        """),
        {
            "user_id": str(currentUser.id),
            "case_id": caseId,
            "result_summary": data.get("summary", ""),
            "result_payload": json.dumps(data),
        },
    )

    db.commit()

    return {
        "summary": data.get("summary", ""),
        "createdSuggestions": created,
        "suggestions": data.get("suggestions", []),
    }


@router.get("/cases/{caseId}/suggestions")
def getSuggestions(
    caseId: str,
    db: Session = Depends(getDb),
    currentUser: User = Depends(getCurrentUser),
):
    verifyCaseAccess(db, currentUser, caseId)

    rows = db.execute(
        text("""
            select
              id,
              suggestion_type,
              priority,
              title,
              reason,
              draft_payload,
              status,
              created_at
            from communication_suggestions
            where case_id = :case_id
              and user_id = :user_id
              and status = 'suggested'
            order by created_at desc
            limit 20
        """),
        {
            "case_id": caseId,
            "user_id": str(currentUser.id),
        },
    ).mappings().all()

    return {"suggestions": [dict(row) for row in rows]}


@router.post("/suggestions/{suggestionId}/convert-to-action")
def convertSuggestionToAction(
    suggestionId: str,
    db: Session = Depends(getDb),
    currentUser: User = Depends(getCurrentUser),
):
    suggestion = db.execute(
        text("""
            select id, case_id, title, draft_payload
            from communication_suggestions
            where id = :suggestion_id
              and user_id = :user_id
              and status = 'suggested'
            limit 1
        """),
        {
            "suggestion_id": suggestionId,
            "user_id": str(currentUser.id),
        },
    ).mappings().first()

    if not suggestion:
        return {"message": "Suggestion not found"}

    verifyCaseAccess(db, currentUser, str(suggestion["case_id"]))

    payload = suggestion["draft_payload"]

    preview = f"""Email Draft

To: {payload.get("toEmail")}
Subject: {payload.get("subject")}

{payload.get("body")}
"""

    action = db.execute(
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
            "case_id": str(suggestion["case_id"]),
            "preview": preview,
            "payload": json.dumps(payload),
        },
    ).mappings().first()

    db.execute(
        text("""
            update communication_suggestions
            set status = 'converted'
            where id = :suggestion_id
        """),
        {"suggestion_id": suggestionId},
    )

    db.commit()

    return {
        "message": "Suggestion converted to pending email action",
        "pendingActionId": str(action["id"]),
    }