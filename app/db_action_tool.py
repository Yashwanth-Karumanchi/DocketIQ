import json
from datetime import date
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models import User
from app.permissions import verifyCaseAccess


def normalizeTaskStatus(value: str | None) -> str:
    lowered = (value or "").strip().lower()

    if lowered in ["complete", "completed", "done"]:
        return "Complete"

    if lowered in ["in progress", "progress", "working"]:
        return "In Progress"

    if lowered in ["cancelled", "canceled", "deleted"]:
        return "Cancelled"

    return "Open"


def normalizePriority(value: str | None) -> str:
    lowered = (value or "").strip().lower()

    if lowered == "high":
        return "High"

    if lowered == "low":
        return "Low"

    return "Medium"


def getTaskId(db: Session, caseId: str, payload: dict) -> str:
    taskId = payload.get("taskId")

    if taskId:
        row = db.execute(
            text("""
                select id
                from case_tasks
                where id = :task_id
                  and case_id = :case_id
                limit 1
            """),
            {
                "task_id": taskId,
                "case_id": caseId,
            },
        ).mappings().first()

        if row:
            return str(row["id"])

    targetTaskTitle = payload.get("targetTaskTitle") or payload.get("title")

    if not targetTaskTitle:
        raise HTTPException(status_code=400, detail="Task ID or task title is required.")

    row = db.execute(
        text("""
            select id
            from case_tasks
            where case_id = :case_id
              and lower(title) like lower(:title_pattern)
            order by created_at desc
            limit 1
        """),
        {
            "case_id": caseId,
            "title_pattern": f"%{targetTaskTitle}%",
        },
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Matching task was not found.")

    return str(row["id"])


def getTargetCaseId(db: Session, currentUser: User, targetCaseNumber: str) -> str:
    row = db.execute(
        text("""
            select c.id
            from cases c
            join case_users cu on cu.case_id = c.id
            where c.case_number = :case_number
              and cu.user_id = :user_id
            limit 1
        """),
        {
            "case_number": targetCaseNumber,
            "user_id": str(currentUser.id),
        },
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Target case was not found or is not accessible.")

    return str(row["id"])


def executeDatabaseAction(
    db: Session,
    currentUser: User,
    caseId: str,
    actionType: str,
    payload: dict,
):
    verifyCaseAccess(db, currentUser, caseId)

    payload = payload or {}

    if actionType == "db_create_task":
        title = payload.get("title")

        if not title:
            raise HTTPException(status_code=400, detail="Task title is required.")

        db.execute(
            text("""
                insert into case_tasks (
                  case_id,
                  title,
                  description,
                  status,
                  priority,
                  due_date
                )
                values (
                  :case_id,
                  :title,
                  :description,
                  :status,
                  :priority,
                  cast(:due_date as date)
                )
            """),
            {
                "case_id": caseId,
                "title": title,
                "description": payload.get("description", ""),
                "status": normalizeTaskStatus(payload.get("status")),
                "priority": normalizePriority(payload.get("priority")),
                "due_date": payload.get("dueDate"),
            },
        )

        return {
            "message": "Task created successfully.",
            "result": {"title": title},
        }

    if actionType == "db_update_task":
        taskId = getTaskId(db, caseId, payload)

        fields = []
        values = {
            "task_id": taskId,
            "case_id": caseId,
        }

        if payload.get("title"):
            fields.append("title = :title")
            values["title"] = payload["title"]

        if payload.get("description") is not None:
            fields.append("description = :description")
            values["description"] = payload["description"]

        if payload.get("status"):
            fields.append("status = :status")
            values["status"] = normalizeTaskStatus(payload["status"])

        if payload.get("priority"):
            fields.append("priority = :priority")
            values["priority"] = normalizePriority(payload["priority"])

        if payload.get("dueDate") is not None:
            fields.append("due_date = cast(:due_date as date)")
            values["due_date"] = payload["dueDate"]

        if not fields:
            raise HTTPException(status_code=400, detail="No task fields were provided to update.")

        db.execute(
            text(f"""
                update case_tasks
                set {", ".join(fields)}
                where id = :task_id
                  and case_id = :case_id
            """),
            values,
        )

        return {
            "message": "Task updated successfully.",
            "result": {"taskId": taskId},
        }

    if actionType == "db_delete_task":
        taskId = getTaskId(db, caseId, payload)

        db.execute(
            text("""
                delete from case_tasks
                where id = :task_id
                  and case_id = :case_id
            """),
            {
                "task_id": taskId,
                "case_id": caseId,
            },
        )

        return {
            "message": "Task deleted successfully.",
            "result": {"taskId": taskId},
        }

    if actionType == "db_update_case":
        allowedFields = {
            "title": "title",
            "status": "status",
            "priority": "priority",
            "summary": "summary",
            "insuranceCompany": "insurance_company",
            "claimNumber": "claim_number",
            "incidentLocation": "incident_location",
        }

        fields = []
        values = {"case_id": caseId}

        for payloadKey, columnName in allowedFields.items():
            if payload.get(payloadKey) is not None:
                fields.append(f"{columnName} = :{payloadKey}")
                if payloadKey == "priority":
                    values[payloadKey] = normalizePriority(payload[payloadKey])
                else:
                    values[payloadKey] = payload[payloadKey]

        if not fields:
            raise HTTPException(status_code=400, detail="No case fields were provided to update.")

        fields.append("updated_at = now()")

        db.execute(
            text(f"""
                update cases
                set {", ".join(fields)}
                where id = :case_id
            """),
            values,
        )

        return {
            "message": "Case updated successfully.",
            "result": {"caseId": caseId},
        }

    if actionType == "db_create_timeline_event":
        title = payload.get("title")

        if not title:
            raise HTTPException(status_code=400, detail="Timeline event title is required.")

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
                  coalesce(cast(:event_date as date), current_date),
                  :event_type,
                  :title,
                  :description,
                  'Chat DB Action'
                )
            """),
            {
                "case_id": caseId,
                "event_date": payload.get("eventDate"),
                "event_type": payload.get("eventType", "Note"),
                "title": title,
                "description": payload.get("description", ""),
            },
        )

        return {
            "message": "Timeline event created successfully.",
            "result": {"title": title},
        }

    if actionType == "db_connect_cases":
        targetCaseNumber = payload.get("targetCaseNumber")

        if not targetCaseNumber:
            raise HTTPException(status_code=400, detail="Target case number is required.")

        targetCaseId = getTargetCaseId(db, currentUser, targetCaseNumber)

        if targetCaseId == caseId:
            raise HTTPException(status_code=400, detail="A case cannot be connected to itself.")

        existing = db.execute(
            text("""
                select id
                from case_relationships
                where
                  (source_case_id = :source_case_id and target_case_id = :target_case_id)
                  or
                  (source_case_id = :target_case_id and target_case_id = :source_case_id)
                limit 1
            """),
            {
                "source_case_id": caseId,
                "target_case_id": targetCaseId,
            },
        ).mappings().first()

        if not existing:
            db.execute(
                text("""
                    insert into case_relationships (
                      source_case_id,
                      target_case_id,
                      relationship_type,
                      description,
                      strength
                    )
                    values (
                      :source_case_id,
                      :target_case_id,
                      :relationship_type,
                      :description,
                      :strength
                    )
                """),
                {
                    "source_case_id": caseId,
                    "target_case_id": targetCaseId,
                    "relationship_type": payload.get("relationshipType", "manual_user_connection"),
                    "description": payload.get("description", "Manually connected by user through DocketIQ chat."),
                    "strength": int(payload.get("strength", 95) or 95),
                },
            )

        return {
            "message": f"Case connected successfully with {targetCaseNumber}.",
            "result": {"targetCaseNumber": targetCaseNumber},
        }

    if actionType == "db_remove_case_connection":
        targetCaseNumber = payload.get("targetCaseNumber")

        if not targetCaseNumber:
            raise HTTPException(status_code=400, detail="Target case number is required.")

        targetCaseId = getTargetCaseId(db, currentUser, targetCaseNumber)

        db.execute(
            text("""
                delete from case_relationships
                where
                  (source_case_id = :source_case_id and target_case_id = :target_case_id)
                  or
                  (source_case_id = :target_case_id and target_case_id = :source_case_id)
            """),
            {
                "source_case_id": caseId,
                "target_case_id": targetCaseId,
            },
        )

        return {
            "message": f"Case connection removed successfully for {targetCaseNumber}.",
            "result": {"targetCaseNumber": targetCaseNumber},
        }

    if actionType == "db_create_communication_suggestion":
        title = payload.get("title")

        if not title:
            raise HTTPException(status_code=400, detail="Communication suggestion title is required.")

        db.execute(
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
            """),
            {
                "user_id": str(currentUser.id),
                "case_id": caseId,
                "suggestion_type": payload.get("suggestionType", "client_follow_up"),
                "priority": normalizePriority(payload.get("priority")),
                "title": title,
                "reason": payload.get("reason", ""),
                "draft_payload": json.dumps(payload.get("draftPayload", {})),
            },
        )

        return {
            "message": "Communication suggestion created successfully.",
            "result": {"title": title},
        }

    raise HTTPException(status_code=400, detail=f"Unsupported database action: {actionType}")