import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.auth import getCurrentUser
from app.db import getDb
from app.models import User
from app.permissions import verifyCaseAccess
from app.gmail_tool import sendGmailEmail
from app.calendar_tool import createCalendarEvent
from app.db_action_tool import executeDatabaseAction

router = APIRouter(prefix="/api/actions", tags=["actions"])

@router.post("/{actionId}/confirm")
def confirmAction(
    actionId: str,
    db: Session = Depends(getDb),
    currentUser: User = Depends(getCurrentUser),
):
    action = db.execute(
        text("""
            select id, user_id, case_id, action_type, status, preview, payload
            from pending_agent_actions
            where id = :action_id
              and user_id = :user_id
            limit 1
        """),
        {
            "action_id": actionId,
            "user_id": str(currentUser.id),
        },
    ).mappings().first()

    if not action:
        raise HTTPException(status_code=404, detail="Pending action not found")

    if action["status"] != "pending":
        raise HTTPException(status_code=409, detail="This action is no longer pending")

    caseId = str(action["case_id"])
    verifyCaseAccess(db, currentUser, caseId)

    payload = action["payload"]

    if isinstance(payload, str):
        payload = json.loads(payload)

    if action["action_type"] == "email_send":
        result = sendGmailEmail(
            db=db,
            currentUser=currentUser,
            toEmail=payload["toEmail"],
            subject=payload["subject"],
            body=payload["body"],
        )

        db.execute(
            text("""
                insert into email_logs (
                  user_id,
                  case_id,
                  to_email,
                  subject,
                  body,
                  google_message_id
                )
                values (
                  :user_id,
                  :case_id,
                  :to_email,
                  :subject,
                  :body,
                  :google_message_id
                )
            """),
            {
                "user_id": str(currentUser.id),
                "case_id": caseId,
                "to_email": payload["toEmail"],
                "subject": payload["subject"],
                "body": payload["body"],
                "google_message_id": result.get("id"),
            },
        )

        db.execute(
            text("""
                insert into tool_calls (
                  user_id,
                  case_id,
                  tool_name,
                  status,
                  request_payload,
                  response_payload
                )
                values (
                  :user_id,
                  :case_id,
                  'gmail_send',
                  'success',
                  cast(:request_payload as jsonb),
                  cast(:response_payload as jsonb)
                )
            """),
            {
                "user_id": str(currentUser.id),
                "case_id": caseId,
                "request_payload": json.dumps(payload),
                "response_payload": json.dumps(result),
            },
        )

        message = "Email sent successfully from your Gmail account."

    elif action["action_type"] == "calendar_create":
        result = createCalendarEvent(
            db=db,
            currentUser=currentUser,
            title=payload["title"],
            description=payload["description"],
            startTime=payload["startTime"],
            endTime=payload["endTime"],
            timeZone=payload.get("timeZone", "America/Denver"),
            attendees=payload.get("attendees", []),
        )

        db.execute(
            text("""
                insert into calendar_logs (
                  user_id,
                  case_id,
                  title,
                  start_time,
                  end_time,
                  attendees,
                  google_event_id,
                  google_event_link
                )
                values (
                  :user_id,
                  :case_id,
                  :title,
                  :start_time,
                  :end_time,
                  cast(:attendees as jsonb),
                  :google_event_id,
                  :google_event_link
                )
            """),
            {
                "user_id": str(currentUser.id),
                "case_id": caseId,
                "title": payload["title"],
                "start_time": payload["startTime"],
                "end_time": payload["endTime"],
                "attendees": json.dumps(payload.get("attendees", [])),
                "google_event_id": result.get("id"),
                "google_event_link": result.get("htmlLink"),
            },
        )

        db.execute(
            text("""
                insert into tool_calls (
                  user_id,
                  case_id,
                  tool_name,
                  status,
                  request_payload,
                  response_payload
                )
                values (
                  :user_id,
                  :case_id,
                  'calendar_create',
                  'success',
                  cast(:request_payload as jsonb),
                  cast(:response_payload as jsonb)
                )
            """),
            {
                "user_id": str(currentUser.id),
                "case_id": caseId,
                "request_payload": json.dumps(payload),
                "response_payload": json.dumps(result),
            },
        )

        message = "Calendar event created successfully from your Google Calendar."

    elif str(action["action_type"]).startswith("db_"):
        result = executeDatabaseAction(
            db=db,
            currentUser=currentUser,
            caseId=caseId,
            actionType=action["action_type"],
            payload=payload,
        )

        message = result.get("message", "Database action completed successfully.")

    else:
        raise HTTPException(status_code=400, detail="Unsupported action type")

    db.execute(
        text("""
            update pending_agent_actions
            set status = 'executed',
                executed_at = :executed_at
            where id = :action_id
        """),
        {
            "action_id": actionId,
            "executed_at": datetime.now(timezone.utc),
        },
    )

    db.execute(
        text("""
            insert into audit_logs (user_id, action, entity_type, entity_id, details)
            values (:user_id, 'agent_action_executed', 'pending_agent_action', :action_id, cast(:details as jsonb))
        """),
        {
            "user_id": str(currentUser.id),
            "action_id": actionId,
            "details": json.dumps({
                "actionType": action["action_type"],
                "caseId": caseId,
            }),
        },
    )

    db.commit()

    return {
        "message": message,
        "actionType": action["action_type"],
    }

@router.post("/{actionId}/cancel")
def cancelAction(
    actionId: str,
    db: Session = Depends(getDb),
    currentUser: User = Depends(getCurrentUser),
):
    action = db.execute(
        text("""
            select id, case_id, status
            from pending_agent_actions
            where id = :action_id
              and user_id = :user_id
            limit 1
        """),
        {
            "action_id": actionId,
            "user_id": str(currentUser.id),
        },
    ).mappings().first()

    if not action:
        raise HTTPException(status_code=404, detail="Pending action not found")

    if action["status"] != "pending":
        raise HTTPException(status_code=409, detail="This action is no longer pending")

    verifyCaseAccess(db, currentUser, str(action["case_id"]))

    db.execute(
        text("""
            update pending_agent_actions
            set status = 'cancelled'
            where id = :action_id
        """),
        {"action_id": actionId},
    )

    db.execute(
        text("""
            insert into audit_logs (user_id, action, entity_type, entity_id, details)
            values (:user_id, 'agent_action_cancelled', 'pending_agent_action', :action_id, cast(:details as jsonb))
        """),
        {
            "user_id": str(currentUser.id),
            "action_id": actionId,
            "details": json.dumps({
                "caseId": str(action["case_id"]),
            }),
        },
    )

    db.commit()

    return {"message": "Action cancelled"}