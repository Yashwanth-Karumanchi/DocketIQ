import json
from datetime import datetime, date
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.auth import getCurrentUser
from app.db import getDb
from app.models import User
from app.permissions import verifyCaseAccess
from app.llm import generateText, parseJsonObject

router = APIRouter(prefix="/api/advanced-agents", tags=["advanced-agents"])


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


def getCaseDocumentContext(db: Session, caseId: str, limit: int = 50) -> str:
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


def getTasks(db: Session, caseId: str) -> list[dict]:
    rows = db.execute(
        text("""
            select title, description, status, priority, due_date, created_at
            from case_tasks
            where case_id = :case_id
            order by created_at desc
            limit 30
        """),
        {"case_id": caseId},
    ).mappings().all()

    return makeJsonSafe([dict(row) for row in rows])


def getTimeline(db: Session, caseId: str) -> list[dict]:
    rows = db.execute(
        text("""
            select event_date, event_type, title, description, source
            from case_timeline_events
            where case_id = :case_id
            order by event_date asc
            limit 40
        """),
        {"case_id": caseId},
    ).mappings().all()

    return makeJsonSafe([dict(row) for row in rows])


def getCommunicationHistory(db: Session, caseId: str) -> dict:
    emailRows = db.execute(
        text("""
            select to_email, subject, created_at
            from email_logs
            where case_id = :case_id
            order by created_at desc
            limit 15
        """),
        {"case_id": caseId},
    ).mappings().all()

    calendarRows = db.execute(
        text("""
            select title, start_time, end_time, attendees, created_at
            from calendar_logs
            where case_id = :case_id
            order by start_time asc
            limit 15
        """),
        {"case_id": caseId},
    ).mappings().all()

    pendingRows = db.execute(
        text("""
            select action_type, status, preview, created_at
            from pending_agent_actions
            where case_id = :case_id
            order by created_at desc
            limit 15
        """),
        {"case_id": caseId},
    ).mappings().all()

    return makeJsonSafe({
        "emails": [dict(row) for row in emailRows],
        "calendarEvents": [dict(row) for row in calendarRows],
        "pendingActions": [dict(row) for row in pendingRows],
    })


def getAccessibleCases(db: Session, currentUser: User, excludeCaseId: str) -> list[dict]:
    rows = db.execute(
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
              cl.phone as client_phone
            from cases c
            join clients cl on cl.id = c.client_id
            join case_users cu on cu.case_id = c.id
            where cu.user_id = :user_id
              and c.id != :case_id
            order by c.created_at desc
            limit 20
        """),
        {
            "user_id": str(currentUser.id),
            "case_id": excludeCaseId,
        },
    ).mappings().all()

    return makeJsonSafe([dict(row) for row in rows])


def saveAgentRun(
    db: Session,
    currentUser: User,
    caseId: str,
    agentName: str,
    resultSummary: str,
    resultPayload: dict,
):
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
              :agent_name,
              'success',
              :result_summary,
              cast(:result_payload as jsonb)
            )
        """),
        {
            "user_id": str(currentUser.id),
            "case_id": caseId,
            "agent_name": agentName,
            "result_summary": resultSummary,
            "result_payload": json.dumps(makeJsonSafe(resultPayload)),
        },
    )


def saveAudit(
    db: Session,
    currentUser: User,
    caseId: str,
    action: str,
    details: dict,
):
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


def createOperationalTask(
    db: Session,
    caseId: str,
    title: str,
    description: str,
    priority: str = "Medium",
):
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
            "title": title,
            "description": description,
            "priority": priority,
        },
    )


@router.post("/cases/{caseId}/readiness")
def runCaseReadinessAgent(
    caseId: str,
    db: Session = Depends(getDb),
    currentUser: User = Depends(getCurrentUser),
):
    verifyCaseAccess(db, currentUser, caseId)

    caseOverview = getCaseOverview(db, caseId)
    documentContext = getCaseDocumentContext(db, caseId)
    tasks = getTasks(db, caseId)
    timeline = getTimeline(db, caseId)
    communication = getCommunicationHistory(db, caseId)

    prompt = f"""
You are DocketIQ's Senior Case Readiness Analyst.

Create a professional attorney-handoff readiness review for a personal-injury legal operations team.

Purpose:
Evaluate whether this case file is operationally ready for attorney review.

Do not provide legal advice.
Do not provide medical advice.
Do not recommend whether to sue, settle, or accept liability.
Use only supplied case data and uploaded document context.
Return only valid JSON.

JSON shape:
{{
  "reportTitle": "Attorney Handoff Readiness Review",
  "executiveSummary": "professional paragraph",
  "readinessScore": 0,
  "handoffStatus": "Not Ready / Partially Ready / Ready",
  "strengths": [
    {{
      "title": "Claim number available",
      "evidence": "MW-894201 appears in case overview"
    }}
  ],
  "blockers": [
    {{
      "title": "Police report missing",
      "severity": "High",
      "whyItMatters": "professional operational explanation",
      "recommendedAction": "specific next step",
      "owner": "Case Manager"
    }}
  ],
  "missingEvidence": [
    {{
      "item": "Medical bills",
      "priority": "High",
      "reason": "professional reason"
    }}
  ],
  "recommendedActions": [
    {{
      "title": "Request treatment records",
      "priority": "High",
      "owner": "Case Manager",
      "expectedOutcome": "Records added to case packet"
    }}
  ],
  "limitations": "what information is unavailable"
}}

Case overview:
{json.dumps(caseOverview, indent=2, default=str)}

Open tasks:
{json.dumps(tasks, indent=2, default=str)}

Timeline:
{json.dumps(timeline, indent=2, default=str)}

Communication history:
{json.dumps(communication, indent=2, default=str)}

Uploaded document context:
{documentContext}
"""

    raw = generateText(prompt)
    data = parseJsonObject(raw)

    for blocker in data.get("blockers", []):
        if blocker.get("severity") == "High":
            createOperationalTask(
                db=db,
                caseId=caseId,
                title=f"[AI Readiness Blocker] {blocker.get('title', 'Readiness blocker')}",
                description=blocker.get("recommendedAction") or blocker.get("whyItMatters") or "",
                priority="High",
            )

    saveAgentRun(
        db=db,
        currentUser=currentUser,
        caseId=caseId,
        agentName="case_readiness",
        resultSummary=data.get("executiveSummary", ""),
        resultPayload=data,
    )

    saveAudit(
        db=db,
        currentUser=currentUser,
        caseId=caseId,
        action="case_readiness_generated",
        details={
            "readinessScore": data.get("readinessScore"),
            "handoffStatus": data.get("handoffStatus"),
            "blockerCount": len(data.get("blockers", [])),
        },
    )

    db.commit()
    return data


@router.post("/cases/{caseId}/contradictions")
def runContradictionAgent(
    caseId: str,
    db: Session = Depends(getDb),
    currentUser: User = Depends(getCurrentUser),
):
    verifyCaseAccess(db, currentUser, caseId)

    caseOverview = getCaseOverview(db, caseId)
    documentContext = getCaseDocumentContext(db, caseId)
    tasks = getTasks(db, caseId)
    timeline = getTimeline(db, caseId)
    communication = getCommunicationHistory(db, caseId)

    prompt = f"""
You are DocketIQ's Case Consistency and Contradiction Analyst.

Review case overview, uploaded documents, tasks, timeline, and communications for mismatches,
uncertainties, inconsistent dates, inconsistent claim numbers, missing identity/contact details,
duplicated facts, and operational contradictions.

Do not provide legal advice.
Do not provide medical advice.
Do not accuse anyone of fraud.
Use careful language: "potential mismatch", "requires verification", "not enough information".
Return only valid JSON.

JSON shape:
{{
  "reportTitle": "Case Consistency Review",
  "executiveSummary": "professional paragraph",
  "consistencyScore": 0,
  "contradictions": [
    {{
      "title": "Incident date mismatch",
      "severity": "High",
      "evidenceA": "Case overview says June 10, 2026",
      "evidenceB": "Uploaded document says June 12, 2026",
      "impact": "why it matters operationally",
      "recommendedAction": "specific verification step"
    }}
  ],
  "uncertaintyItems": [
    {{
      "title": "Adjuster contact not available",
      "severity": "Medium",
      "explanation": "professional explanation",
      "recommendedAction": "specific next step"
    }}
  ],
  "verifiedConsistentFacts": [
    {{
      "fact": "Claim number MW-894201",
      "evidence": "case overview and document context align"
    }}
  ],
  "nextOperationalSteps": [
    "step 1",
    "step 2"
  ],
  "limitations": "what could not be checked"
}}

Case overview:
{json.dumps(caseOverview, indent=2, default=str)}

Tasks:
{json.dumps(tasks, indent=2, default=str)}

Timeline:
{json.dumps(timeline, indent=2, default=str)}

Communication history:
{json.dumps(communication, indent=2, default=str)}

Uploaded document context:
{documentContext}
"""

    raw = generateText(prompt)
    data = parseJsonObject(raw)

    for contradiction in data.get("contradictions", []):
        if contradiction.get("severity") in ["High", "Critical"]:
            createOperationalTask(
                db=db,
                caseId=caseId,
                title=f"[AI Consistency Check] {contradiction.get('title', 'Potential contradiction')}",
                description=contradiction.get("recommendedAction") or contradiction.get("impact") or "",
                priority="High",
            )

    saveAgentRun(
        db=db,
        currentUser=currentUser,
        caseId=caseId,
        agentName="contradiction_consistency",
        resultSummary=data.get("executiveSummary", ""),
        resultPayload=data,
    )

    saveAudit(
        db=db,
        currentUser=currentUser,
        caseId=caseId,
        action="contradiction_review_generated",
        details={
            "consistencyScore": data.get("consistencyScore"),
            "contradictionCount": len(data.get("contradictions", [])),
            "uncertaintyCount": len(data.get("uncertaintyItems", [])),
        },
    )

    db.commit()
    return data


@router.post("/cases/{caseId}/next-best-actions")
def runNextBestActionAgent(
    caseId: str,
    db: Session = Depends(getDb),
    currentUser: User = Depends(getCurrentUser),
):
    verifyCaseAccess(db, currentUser, caseId)

    caseOverview = getCaseOverview(db, caseId)
    documentContext = getCaseDocumentContext(db, caseId)
    tasks = getTasks(db, caseId)
    timeline = getTimeline(db, caseId)
    communication = getCommunicationHistory(db, caseId)

    prompt = f"""
You are DocketIQ's Senior Legal Operations Next Best Action Planner.

Create a prioritized, practical action plan for the case manager.

Focus on:
- What moves the case forward today
- Missing documents
- Follow-up communications
- Calendar scheduling
- Case readiness
- Operational blockers

Do not provide legal advice.
Do not provide medical advice.
Do not recommend legal strategy.
Return only valid JSON.

JSON shape:
{{
  "reportTitle": "Next Best Action Plan",
  "executiveSummary": "professional paragraph",
  "overallPriority": "Low / Medium / High",
  "topActions": [
    {{
      "rank": 1,
      "title": "Request police report from client",
      "priority": "High",
      "owner": "Case Manager",
      "whyNow": "professional reason",
      "expectedOutcome": "specific outcome",
      "recommendedChannel": "Email",
      "suggestedCommunication": "short professional message guidance"
    }}
  ],
  "automationOpportunities": [
    {{
      "title": "Prepare missing document email",
      "tool": "Communication Autopilot",
      "reason": "why automation helps"
    }}
  ],
  "doNotDoYet": [
    {{
      "title": "Generate final handoff",
      "reason": "missing police report and treatment records"
    }}
  ],
  "nextReviewTrigger": "when the next review should happen"
}}

Case overview:
{json.dumps(caseOverview, indent=2, default=str)}

Tasks:
{json.dumps(tasks, indent=2, default=str)}

Timeline:
{json.dumps(timeline, indent=2, default=str)}

Communication history:
{json.dumps(communication, indent=2, default=str)}

Uploaded document context:
{documentContext}
"""

    raw = generateText(prompt)
    data = parseJsonObject(raw)

    for action in data.get("topActions", [])[:5]:
        createOperationalTask(
            db=db,
            caseId=caseId,
            title=f"[AI Next Best Action] {action.get('title', 'Recommended action')}",
            description=(
                f"Why now: {action.get('whyNow', '')}\n"
                f"Expected outcome: {action.get('expectedOutcome', '')}\n"
                f"Suggested communication: {action.get('suggestedCommunication', '')}"
            ),
            priority=action.get("priority", "Medium"),
        )

    saveAgentRun(
        db=db,
        currentUser=currentUser,
        caseId=caseId,
        agentName="next_best_action",
        resultSummary=data.get("executiveSummary", ""),
        resultPayload=data,
    )

    saveAudit(
        db=db,
        currentUser=currentUser,
        caseId=caseId,
        action="next_best_actions_generated",
        details={
            "overallPriority": data.get("overallPriority"),
            "actionCount": len(data.get("topActions", [])),
        },
    )

    db.commit()
    return data


@router.post("/cases/{caseId}/relationships")
def runCaseRelationshipAgent(
    caseId: str,
    db: Session = Depends(getDb),
    currentUser: User = Depends(getCurrentUser),
):
    verifyCaseAccess(db, currentUser, caseId)

    caseOverview = getCaseOverview(db, caseId)
    otherCases = getAccessibleCases(db, currentUser, caseId)
    documentContext = getCaseDocumentContext(db, caseId, limit=20)

    prompt = f"""
You are DocketIQ's Case Relationship Analyst.

Compare the selected case against other cases the user can access.

Find possible operational relationships such as:
- Same client
- Same accident date
- Same insurance company
- Same claim number
- Same provider
- Same vehicle/property damage context
- Shared witness or location
- Duplicate or related intake

Do not expose unauthorized case data.
Do not provide legal advice.
Do not overstate weak relationships.
Use confidence and clear reasoning.
Return only valid JSON.

JSON shape:
{{
  "reportTitle": "Case Relationship Review",
  "executiveSummary": "professional paragraph",
  "relationships": [
    {{
      "targetCaseNumber": "CL-24245571",
      "relationshipType": "Same insurer",
      "strength": 2,
      "confidence": "Medium",
      "description": "professional explanation",
      "operationalValue": "why this relationship helps case management"
    }}
  ],
  "noRelationshipFindings": [
    "No shared claim number found"
  ],
  "recommendedActions": [
    "Review related case documents for duplicate intake details"
  ],
  "limitations": "what could not be compared"
}}

Selected case:
{json.dumps(caseOverview, indent=2, default=str)}

Other accessible cases:
{json.dumps(otherCases, indent=2, default=str)}

Selected case document context:
{documentContext}
"""

    raw = generateText(prompt)
    data = parseJsonObject(raw)

    db.execute(
        text("""
            delete from case_relationships
            where source_case_id = :case_id
        """),
        {"case_id": caseId},
    )

    insertedRelationships = 0

    for relationship in data.get("relationships", []):
        targetCaseNumber = relationship.get("targetCaseNumber")

        if not targetCaseNumber:
            continue

        target = db.execute(
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

        if not target:
            continue

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
                "target_case_id": str(target["id"]),
                "relationship_type": relationship.get("relationshipType", "Related case"),
                "description": relationship.get("description", ""),
                "strength": int(relationship.get("strength", 1) or 1),
            },
        )

        insertedRelationships += 1

    saveAgentRun(
        db=db,
        currentUser=currentUser,
        caseId=caseId,
        agentName="case_relationship",
        resultSummary=data.get("executiveSummary", ""),
        resultPayload=data,
    )

    saveAudit(
        db=db,
        currentUser=currentUser,
        caseId=caseId,
        action="case_relationships_generated",
        details={
            "relationshipCount": insertedRelationships,
        },
    )

    db.commit()

    data["insertedRelationshipCount"] = insertedRelationships
    return data