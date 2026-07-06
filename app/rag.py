import json
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.auth import getCurrentUser
from app.db import getDb
from app.models import User
from app.permissions import verifyCaseAccess
from app.firewall import runFirewall
from app.llm import createEmbedding, generateText, toPgVector, cleanAssistantText
from app.action_agent import createPendingActionFromMessage

router = APIRouter(prefix="/api/rag", tags=["rag"])

def getGlobalOperationalContext(db: Session, currentUser: User) -> str:
    statsRow = db.execute(
        text("""
            select
              count(distinct c.id) as total_cases,
              count(distinct c.id) filter (where c.priority = 'High') as high_priority_cases,
              count(distinct ct.id) filter (where ct.status = 'Open') as open_tasks,
              count(distinct paa.id) filter (where paa.status = 'pending') as pending_actions,
              count(distinct d.id) as document_count
            from cases c
            join case_users cu on cu.case_id = c.id
            left join case_tasks ct on ct.case_id = c.id
            left join pending_agent_actions paa on paa.case_id = c.id
            left join documents d on d.case_id = c.id
            where cu.user_id = :user_id
        """),
        {"user_id": str(currentUser.id)},
    ).mappings().first()

    caseRows = db.execute(
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
              count(distinct ct.id) filter (where ct.status = 'Open') as open_task_count,
              count(distinct paa.id) filter (where paa.status = 'pending') as pending_action_count,
              count(distinct d.id) as document_count
            from cases c
            join clients cl on cl.id = c.client_id
            join case_users cu on cu.case_id = c.id
            left join case_tasks ct on ct.case_id = c.id
            left join pending_agent_actions paa on paa.case_id = c.id
            left join documents d on d.case_id = c.id
            where cu.user_id = :user_id
            group by c.id, cl.id
            order by
              case when c.priority = 'High' then 1
                   when c.priority = 'Medium' then 2
                   else 3
              end,
              c.created_at desc
            limit 75
        """),
        {"user_id": str(currentUser.id)},
    ).mappings().all()

    pendingRows = db.execute(
        text("""
            select
              paa.action_type,
              paa.status,
              paa.preview,
              paa.created_at,
              c.case_number,
              cl.full_name as client_name
            from pending_agent_actions paa
            join cases c on c.id = paa.case_id
            join clients cl on cl.id = c.client_id
            join case_users cu on cu.case_id = c.id
            where cu.user_id = :user_id
              and paa.status = 'pending'
            order by paa.created_at desc
            limit 25
        """),
        {"user_id": str(currentUser.id)},
    ).mappings().all()

    activityRows = db.execute(
        text("""
            select action, entity_type, details, created_at
            from audit_logs
            where user_id = :user_id
            order by created_at desc
            limit 25
        """),
        {"user_id": str(currentUser.id)},
    ).mappings().all()

    agentRows = db.execute(
        text("""
            select
              ar.agent_name,
              ar.result_summary,
              ar.created_at,
              c.case_number,
              cl.full_name as client_name
            from agent_runs ar
            join cases c on c.id = ar.case_id
            join clients cl on cl.id = c.client_id
            join case_users cu on cu.case_id = c.id
            where cu.user_id = :user_id
            order by ar.created_at desc
            limit 25
        """),
        {"user_id": str(currentUser.id)},
    ).mappings().all()

    context = {
        "dashboardStats": dict(statsRow) if statsRow else {},
        "accessibleCases": [dict(row) for row in caseRows],
        "pendingActions": [dict(row) for row in pendingRows],
        "recentActivity": [dict(row) for row in activityRows],
        "recentAgentRuns": [dict(row) for row in agentRows],
    }

    return json.dumps(context, indent=2, default=str)

def getCaseOperationalContext(db: Session, currentUser: User, caseId: str) -> str:
    caseRow = db.execute(
        text("""
            select
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

    taskRows = db.execute(
        text("""
            select title, description, status, priority, due_date, created_at
            from case_tasks
            where case_id = :case_id
            order by created_at desc
            limit 25
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

    calendarRows = db.execute(
        text("""
            select title, start_time, end_time, attendees
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

    connectedRows = db.execute(
        text("""
            select
              cr.id,
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
              end as connected_client_name,
              case
                when cr.source_case_id = :case_id then target_case.insurance_company
                else source_case.insurance_company
              end as connected_insurance_company,
              case
                when cr.source_case_id = :case_id then target_case.claim_number
                else source_case.claim_number
              end as connected_claim_number
            from case_relationships cr
            join cases source_case on source_case.id = cr.source_case_id
            join clients source_client on source_client.id = source_case.client_id
            join cases target_case on target_case.id = cr.target_case_id
            join clients target_client on target_client.id = target_case.client_id
            join case_users cu on cu.case_id = case
              when cr.source_case_id = :case_id then cr.target_case_id
              else cr.source_case_id
            end
            where (cr.source_case_id = :case_id or cr.target_case_id = :case_id)
              and cu.user_id = :user_id
            order by cr.strength desc nulls last, cr.created_at desc
            limit 20
        """),
        {
            "case_id": caseId,
            "user_id": str(currentUser.id),
        },
    ).mappings().all()

    memorySummary = getChatMemory(db, currentUser, caseId)

    context = {
        "caseOverview": dict(caseRow) if caseRow else {},
        "openTasksAndMissingItems": [dict(row) for row in taskRows],
        "timeline": [dict(row) for row in timelineRows],
        "calendarEvents": [dict(row) for row in calendarRows],
        "pendingActions": [dict(row) for row in pendingRows],
        "connectedCases": [dict(row) for row in connectedRows],
        "privateCaseMemory": memorySummary,
    }

    return json.dumps(context, indent=2, default=str)

def getChatMemory(db: Session, currentUser: User, caseId: str) -> str:
    row = db.execute(
        text("""
            select memory_summary
            from chat_memories
            where user_id = :user_id
              and case_id = :case_id
            limit 1
        """),
        {
            "user_id": str(currentUser.id),
            "case_id": caseId,
        },
    ).mappings().first()

    return row["memory_summary"] if row else ""


def updateChatMemory(
    db: Session,
    currentUser: User,
    caseId: str,
    userMessage: str,
    assistantMessage: str,
):
    existingMemory = getChatMemory(db, currentUser, caseId)

    prompt = f"""
You are DocketIQ's memory manager.

Update the private working memory for this user and case.

Rules:
- Keep only durable useful facts.
- Do not include long chat transcripts.
- Remember preferences, completed actions, pending actions, known missing items, and important case context.
- Keep it concise.
- Do not include legal advice.

Existing memory:
{existingMemory}

New user message:
{userMessage}

New assistant response:
{assistantMessage}

Return only the updated memory summary.
"""

    newMemory = cleanAssistantText(generateText(prompt).strip())

    db.execute(
        text("""
            insert into chat_memories (
              user_id,
              case_id,
              memory_summary,
              updated_at
            )
            values (
              :user_id,
              :case_id,
              :memory_summary,
              now()
            )
            on conflict (user_id, case_id)
            do update set
              memory_summary = excluded.memory_summary,
              updated_at = now()
        """),
        {
            "user_id": str(currentUser.id),
            "case_id": caseId,
            "memory_summary": newMemory,
        },
    )

class ChatRequest(BaseModel):
    message: str

def saveFirewallDecision(
    db: Session,
    currentUser: User,
    caseId: str,
    message: str,
    firewall,
):
    db.execute(
        text("""
            insert into firewall_decisions (
              user_id,
              case_id,
              message,
              decision,
              risk_level,
              reason,
              allowed_tools,
              raw_response
            )
            values (
              :user_id,
              :case_id,
              :message,
              :decision,
              :risk_level,
              :reason,
              cast(:allowed_tools as jsonb),
              cast(:raw_response as jsonb)
            )
        """),
        {
            "user_id": str(currentUser.id),
            "case_id": caseId,
            "message": message,
            "decision": firewall.decision,
            "risk_level": firewall.riskLevel,
            "reason": firewall.reason,
            "allowed_tools": json.dumps(firewall.allowedTools),
            "raw_response": firewall.model_dump_json(),
        },
    )

def retrieveCaseChunks(db: Session, caseId: str, question: str, limit: int = 6):
    embedding = createEmbedding(question)
    vectorValue = toPgVector(embedding)

    rows = db.execute(
        text("""
            select
              dc.id,
              dc.content,
              dc.chunk_index,
              d.file_name,
              1 - (dc.embedding <=> cast(:embedding as vector)) as similarity
            from document_chunks dc
            join documents d on d.id = dc.document_id
            where dc.case_id = :case_id
            order by dc.embedding <=> cast(:embedding as vector)
            limit :limit
        """),
        {
            "case_id": caseId,
            "embedding": vectorValue,
            "limit": limit,
        },
    ).mappings().all()

    return [dict(row) for row in rows]

@router.post("/chat")
def chatWithDashboard(
    payload: ChatRequest,
    db: Session = Depends(getDb),
    currentUser: User = Depends(getCurrentUser),
):
    firewall = runFirewall(payload.message)

    if firewall.decision == "refuse":
        return {
            "answer": (
                "I can help with legal operations questions across your dashboard, "
                "including case counts, high-priority cases, missing items, pending actions, "
                "calendar status, and reports. I cannot help with this request because: "
                f"{firewall.reason}"
            ),
            "sources": [{"fileName": "dashboard_context", "chunkIndex": None, "similarity": None}],
            "firewall": firewall.model_dump(),
        }

    if firewall.decision == "require_confirmation":
        return {
            "answer": (
                "This action needs a selected case before I can prepare it. "
                "Please open the relevant case workspace first, then ask me to draft the email, "
                "create the calendar event, or prepare the action."
            ),
            "sources": [{"fileName": "dashboard_context", "chunkIndex": None, "similarity": None}],
            "firewall": firewall.model_dump(),
        }

    dashboardContext = getGlobalOperationalContext(db, currentUser)

    prompt = f"""
You are DocketIQ, a legal operations AI assistant.

The user has not selected a specific case. Answer from dashboard-level context.

You can answer:
- How many cases exist
- How many high-priority cases exist
- Which cases are high priority
- Which cases have open tasks
- Which cases have documents
- Which cases have pending actions
- Recent activity
- Recent agent runs
- Portfolio-level summaries
- Which case the user should open next from an operational perspective

Rules:
- Do not say a case is selected.
- If the user asks for a specific case action, tell them to open that case first.
- Do not provide legal advice.
- Do not provide medical advice.
- Do not use Markdown formatting.
- Do not use asterisks.
- Write clean plain text.
- Use simple section labels.
- Use hyphen bullets only.

User question:
{payload.message}

Dashboard context:
{dashboardContext}
"""

    answer = cleanAssistantText(generateText(prompt))

    return {
        "answer": answer,
        "sources": [{"fileName": "dashboard_context", "chunkIndex": None, "similarity": None}],
        "firewall": firewall.model_dump(),
    }
    

def isDataManagementIntent(message: str) -> bool:
    lowered = message.lower()

    dataWords = [
        "add task",
        "create task",
        "update task",
        "change task",
        "mark task",
        "mark the",
        "complete task",
        "close task",
        "delete task",
        "remove task",
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

    return any(word in lowered for word in dataWords)


@router.post("/cases/{caseId}/chat")
def chatWithCase(
    caseId: str,
    payload: ChatRequest,
    db: Session = Depends(getDb),
    currentUser: User = Depends(getCurrentUser),
):
    verifyCaseAccess(db, currentUser, caseId)
    memorySummary = getChatMemory(db, currentUser, caseId)

    firewall = runFirewall(payload.message)
    saveFirewallDecision(db, currentUser, caseId, payload.message, firewall)

    if firewall.decision == "refuse":
        answer = (
            "I can help with legal operations tasks like summarizing case documents, "
            "tracking missing items, and preparing case handoff information. "
            f"I can’t help with this request because: {firewall.reason}"
        )

        db.commit()

        return {
            "answer": answer,
            "sources": [],
            "firewall": firewall.model_dump(),
        }

    if firewall.decision == "ask_clarifying":
        answer = f"I need one clarification before I can help: {firewall.reason}"
        db.commit()

        return {
            "answer": answer,
            "sources": [],
            "firewall": firewall.model_dump(),
        }

    if firewall.decision == "require_confirmation":
        actionResult = createPendingActionFromMessage(
            db=db,
            currentUser=currentUser,
            caseId=caseId,
            userMessage=payload.message,
        )

        if actionResult.get("needsClarification"):
            answer = actionResult["message"]

            db.execute(
                text("""
                    insert into agent_messages (
                    user_id,
                    case_id,
                    user_message,
                    assistant_message,
                    sources
                    )
                    values (
                    :user_id,
                    :case_id,
                    :user_message,
                    :assistant_message,
                    cast(:sources as jsonb)
                    )
                """),
                {
                    "user_id": str(currentUser.id),
                    "case_id": caseId,
                    "user_message": payload.message,
                    "assistant_message": answer,
                    "sources": json.dumps([]),
                },
            )

            db.commit()

            return {
                "answer": answer,
                "sources": [],
                "firewall": firewall.model_dump(),
            }

        pendingAction = actionResult["pendingAction"]
        answer = (
            "I prepared this action for your review. "
            "Please confirm before I execute it from your Google account.\n\n"
            + pendingAction["preview"]
        )

        db.execute(
            text("""
                insert into agent_messages (
                user_id,
                case_id,
                user_message,
                assistant_message,
                sources
                )
                values (
                :user_id,
                :case_id,
                :user_message,
                :assistant_message,
                cast(:sources as jsonb)
                )
            """),
            {
                "user_id": str(currentUser.id),
                "case_id": caseId,
                "user_message": payload.message,
                "assistant_message": answer,
                "sources": json.dumps([]),
            },
        )

        db.execute(
            text("""
                insert into audit_logs (user_id, action, entity_type, entity_id, details)
                values (:user_id, 'pending_agent_action_created', 'case', :case_id, cast(:details as jsonb))
            """),
            {
                "user_id": str(currentUser.id),
                "case_id": caseId,
                "details": json.dumps({
                    "pendingActionId": pendingAction["id"],
                    "type": pendingAction["type"],
                }),
            },
        )
        
        updateChatMemory(
            db=db,
            currentUser=currentUser,
            caseId=caseId,
            userMessage=payload.message,
            assistantMessage=answer,
        )

        db.commit()

        return {
            "answer": answer,
            "sources": [],
            "firewall": firewall.model_dump(),
            "pendingAction": pendingAction,
        }

    if isDataManagementIntent(payload.message):
        actionResult = createPendingActionFromMessage(
            db=db,
            currentUser=currentUser,
            caseId=caseId,
            userMessage=payload.message,
        )

        if actionResult.get("needsClarification"):
            answer = actionResult["message"]

            db.execute(
                text("""
                    insert into agent_messages (
                      user_id,
                      case_id,
                      user_message,
                      assistant_message,
                      sources
                    )
                    values (
                      :user_id,
                      :case_id,
                      :user_message,
                      :assistant_message,
                      cast(:sources as jsonb)
                    )
                """),
                {
                    "user_id": str(currentUser.id),
                    "case_id": caseId,
                    "user_message": payload.message,
                    "assistant_message": answer,
                    "sources": json.dumps([]),
                },
            )

            db.commit()

            return {
                "answer": answer,
                "sources": [],
                "firewall": firewall.model_dump(),
            }

        pendingAction = actionResult["pendingAction"]
        answer = (
            "I prepared this case-data update for your review. "
            "Please confirm before I change the database.\n\n"
            + pendingAction["preview"]
        )

        db.execute(
            text("""
                insert into agent_messages (
                  user_id,
                  case_id,
                  user_message,
                  assistant_message,
                  sources
                )
                values (
                  :user_id,
                  :case_id,
                  :user_message,
                  :assistant_message,
                  cast(:sources as jsonb)
                )
            """),
            {
                "user_id": str(currentUser.id),
                "case_id": caseId,
                "user_message": payload.message,
                "assistant_message": answer,
                "sources": json.dumps([]),
            },
        )

        db.execute(
            text("""
                insert into audit_logs (user_id, action, entity_type, entity_id, details)
                values (:user_id, 'pending_db_action_created', 'case', :case_id, cast(:details as jsonb))
            """),
            {
                "user_id": str(currentUser.id),
                "case_id": caseId,
                "details": json.dumps({
                    "pendingActionId": pendingAction["id"],
                    "type": pendingAction["type"],
                }),
            },
        )

        updateChatMemory(
            db=db,
            currentUser=currentUser,
            caseId=caseId,
            userMessage=payload.message,
            assistantMessage=answer,
        )

        db.commit()

        return {
            "answer": answer,
            "sources": [],
            "firewall": firewall.model_dump(),
            "pendingAction": pendingAction,
        }
    chunks = retrieveCaseChunks(db, caseId, payload.message)

    contextBlocks = []
    operationalContext = getCaseOperationalContext(db, currentUser, caseId)

    for index, chunk in enumerate(chunks):
        contextBlocks.append(
            f"""
SOURCE {index + 1}
File: {chunk["file_name"]}
Chunk: {chunk["chunk_index"]}
Content:
{chunk["content"]}
"""
        )

    context = "\n\n".join(contextBlocks)

    prompt = f"""
You are DocketIQ, a legal operations AI assistant for personal-injury case teams.

Use ALL available case context:
1. Case overview
2. Tasks and missing items
3. Timeline events
4. Calendar events
5. Pending actions
6. Connected cases and relationship records
7. Private user/case memory
8. Uploaded document excerpts, if any are available

Rules:
- The user is asking about the selected case unless they explicitly name another case.
- Answer from available case records.
- If uploaded documents are missing, still answer from structured case data.
- Clearly say when a fact is not available.
- Do not provide legal advice.
- Do not provide medical advice or diagnosis.
- Do not recommend whether to sue, settle, accept liability, or choose legal strategy.
- Be professional, practical, and operational.
- Do not use Markdown formatting.
- Do not use asterisks.
- Do not use bold text markers.
- Do not say "Hello, I am DocketIQ."
- Write in clean plain text.
- Use simple section labels like "Case Overview:" instead of markdown headings.
- Use hyphen bullets only when listing items.

User question:
{payload.message}

Structured case operations context:
{operationalContext}

Uploaded document context:
{context if chunks else "No uploaded document excerpts are available yet."}
"""

    answer = generateText(prompt)

    sources = [
        {
            "fileName": chunk["file_name"],
            "chunkIndex": chunk["chunk_index"],
            "similarity": float(chunk["similarity"]) if chunk["similarity"] is not None else None,
        }
        for chunk in chunks
    ]

    db.execute(
        text("""
            insert into agent_messages (
              user_id,
              case_id,
              user_message,
              assistant_message,
              sources
            )
            values (
              :user_id,
              :case_id,
              :user_message,
              :assistant_message,
              cast(:sources as jsonb)
            )
        """),
        {
            "user_id": str(currentUser.id),
            "case_id": caseId,
            "user_message": payload.message,
            "assistant_message": answer,
            "sources": json.dumps(sources),
        },
    )

    db.execute(
        text("""
            insert into audit_logs (user_id, action, entity_type, entity_id, details)
            values (:user_id, 'rag_chat_answered', 'case', :case_id, cast(:details as jsonb))
        """),
        {
            "user_id": str(currentUser.id),
            "case_id": caseId,
            "details": json.dumps({
                "question": payload.message,
                "sourceCount": len(sources),
                "firewallDecision": firewall.decision,
            }),
        },
    )
    
    updateChatMemory(
        db=db,
        currentUser=currentUser,
        caseId=caseId,
        userMessage=payload.message,
        assistantMessage=answer,
    )

    db.commit()

    return {
        "answer": answer,
        "sources": sources,
        "firewall": firewall.model_dump(),
    }