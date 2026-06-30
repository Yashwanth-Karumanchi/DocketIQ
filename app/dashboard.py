from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.auth import getCurrentUser
from app.db import getDb
from app.models import User

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def getDashboard(
    db: Session = Depends(getDb),
    currentUser: User = Depends(getCurrentUser),
):
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
              cl.email as client_email,
              count(distinct d.id) as document_count,
              count(distinct ct.id) filter (where ct.status = 'Open') as open_task_count,
              count(distinct paa.id) filter (where paa.status = 'pending') as pending_action_count
            from cases c
            join clients cl on cl.id = c.client_id
            join case_users cu on cu.case_id = c.id
            left join documents d on d.case_id = c.id
            left join case_tasks ct on ct.case_id = c.id
            left join pending_agent_actions paa on paa.case_id = c.id
            where cu.user_id = :user_id
            group by c.id, cl.id
            order by c.created_at desc
        """),
        {"user_id": str(currentUser.id)},
    ).mappings().all()

    calendarRows = db.execute(
        text("""
            select
              id,
              case_id,
              title,
              start_time,
              end_time,
              attendees,
              google_event_link,
              created_at
            from calendar_logs
            where user_id = :user_id
            order by start_time asc
            limit 10
        """),
        {"user_id": str(currentUser.id)},
    ).mappings().all()

    pendingRows = db.execute(
        text("""
            select
              paa.id,
              paa.case_id,
              paa.action_type,
              paa.preview,
              paa.status,
              paa.created_at,
              c.case_number,
              cl.full_name as client_name
            from pending_agent_actions paa
            join cases c on c.id = paa.case_id
            join clients cl on cl.id = c.client_id
            where paa.user_id = :user_id
              and paa.status = 'pending'
            order by paa.created_at desc
            limit 10
        """),
        {"user_id": str(currentUser.id)},
    ).mappings().all()

    activityRows = db.execute(
        text("""
            select action, entity_type, entity_id, details, created_at
            from audit_logs
            where user_id = :user_id
            order by created_at desc
            limit 15
        """),
        {"user_id": str(currentUser.id)},
    ).mappings().all()

    cases = [dict(row) for row in caseRows]

    totalCases = len(cases)
    highPriority = len([case for case in cases if case["priority"] == "High"])
    openTasks = sum(int(case["open_task_count"] or 0) for case in cases)
    pendingActions = sum(int(case["pending_action_count"] or 0) for case in cases)
    documentCount = sum(int(case["document_count"] or 0) for case in cases)

    return {
        "stats": {
            "totalCases": totalCases,
            "highPriority": highPriority,
            "openTasks": openTasks,
            "pendingActions": pendingActions,
            "documentCount": documentCount,
        },
        "cases": cases,
        "calendarEvents": [dict(row) for row in calendarRows],
        "pendingActions": [dict(row) for row in pendingRows],
        "recentActivity": [dict(row) for row in activityRows],
    }


@router.get("/cases/{caseId}/graph")
def getCaseGraph(
    caseId: str,
    db: Session = Depends(getDb),
    currentUser: User = Depends(getCurrentUser),
):
    access = db.execute(
        text("""
            select id
            from case_users
            where case_id = :case_id
              and user_id = :user_id
            limit 1
        """),
        {
            "case_id": caseId,
            "user_id": str(currentUser.id),
        },
    ).first()

    if not access:
        return {"nodes": [], "edges": []}

    caseRow = db.execute(
        text("""
            select
              c.id,
              c.case_number,
              c.title,
              cl.full_name as client_name
            from cases c
            join clients cl on cl.id = c.client_id
            where c.id = :case_id
        """),
        {"case_id": caseId},
    ).mappings().first()

    documentRows = db.execute(
        text("""
            select id, file_name, status
            from documents
            where case_id = :case_id
            order by created_at desc
        """),
        {"case_id": caseId},
    ).mappings().all()

    taskRows = db.execute(
        text("""
            select id, title, priority, status
            from case_tasks
            where case_id = :case_id
            order by created_at desc
            limit 10
        """),
        {"case_id": caseId},
    ).mappings().all()

    relatedRows = db.execute(
        text("""
            select
              cr.id,
              cr.relationship_type,
              cr.description,
              cr.target_case_id,
              c.case_number,
              c.title
            from case_relationships cr
            join cases c on c.id = cr.target_case_id
            join case_users cu on cu.case_id = c.id
            where cr.source_case_id = :case_id
              and cu.user_id = :user_id
        """),
        {
            "case_id": caseId,
            "user_id": str(currentUser.id),
        },
    ).mappings().all()

    nodes = []
    edges = []

    if caseRow:
        nodes.append({
            "id": str(caseRow["id"]),
            "label": caseRow["case_number"],
            "subtitle": caseRow["client_name"],
            "type": "case",
        })

    for doc in documentRows:
        nodeId = f"doc-{doc['id']}"
        nodes.append({
            "id": nodeId,
            "label": doc["file_name"],
            "subtitle": doc["status"],
            "type": "document",
        })
        edges.append({
            "source": str(caseId),
            "target": nodeId,
            "label": "document",
        })

    for task in taskRows:
        nodeId = f"task-{task['id']}"
        nodes.append({
            "id": nodeId,
            "label": task["title"],
            "subtitle": f"{task['priority']} · {task['status']}",
            "type": "task",
        })
        edges.append({
            "source": str(caseId),
            "target": nodeId,
            "label": "task",
        })

    for related in relatedRows:
        relatedId = str(related["target_case_id"])
        nodes.append({
            "id": relatedId,
            "label": related["case_number"],
            "subtitle": related["title"],
            "type": "related_case",
        })
        edges.append({
            "source": str(caseId),
            "target": relatedId,
            "label": related["relationship_type"],
        })

    return {
        "nodes": nodes,
        "edges": edges,
    }
    
@router.get("/cases/{caseId}/timeline")
def getCaseTimeline(
    caseId: str,
    db: Session = Depends(getDb),
    currentUser: User = Depends(getCurrentUser),
):
    access = db.execute(
        text("""
            select id
            from case_users
            where case_id = :case_id
              and user_id = :user_id
            limit 1
        """),
        {
            "case_id": caseId,
            "user_id": str(currentUser.id),
        },
    ).first()

    if not access:
        return {"timeline": []}

    rows = db.execute(
        text("""
            select
              id,
              event_date,
              event_type,
              title,
              description,
              source,
              created_at
            from case_timeline_events
            where case_id = :case_id
            order by event_date asc, created_at asc
        """),
        {"case_id": caseId},
    ).mappings().all()

    return {"timeline": [dict(row) for row in rows]}

@router.get("/cases/{caseId}/tasks")
def getCaseTasks(
    caseId: str,
    db: Session = Depends(getDb),
    currentUser: User = Depends(getCurrentUser),
):
    access = db.execute(
        text("""
            select id
            from case_users
            where case_id = :case_id
              and user_id = :user_id
            limit 1
        """),
        {
            "case_id": caseId,
            "user_id": str(currentUser.id),
        },
    ).first()

    if not access:
        return {"tasks": []}

    rows = db.execute(
        text("""
            select
              id,
              title,
              description,
              status,
              priority,
              due_date,
              created_at
            from case_tasks
            where case_id = :case_id
            order by
              case when priority = 'High' then 1
                   when priority = 'Medium' then 2
                   else 3
              end,
              created_at desc
        """),
        {"case_id": caseId},
    ).mappings().all()

    return {"tasks": [dict(row) for row in rows]}


@router.get("/cases/{caseId}/reports")
def getCaseReports(
    caseId: str,
    db: Session = Depends(getDb),
    currentUser: User = Depends(getCurrentUser),
):
    access = db.execute(
        text("""
            select id
            from case_users
            where case_id = :case_id
              and user_id = :user_id
            limit 1
        """),
        {
            "case_id": caseId,
            "user_id": str(currentUser.id),
        },
    ).first()

    if not access:
        return {"reports": [], "agentRuns": []}

    reportRows = db.execute(
        text("""
            select
              id,
              report_type,
              title,
              summary,
              created_at
            from report_logs
            where case_id = :case_id
            order by created_at desc
            limit 20
        """),
        {"case_id": caseId},
    ).mappings().all()

    runRows = db.execute(
        text("""
            select
              id,
              agent_name,
              status,
              result_summary,
              result_payload,
              created_at
            from agent_runs
            where case_id = :case_id
            order by created_at desc
            limit 30
        """),
        {"case_id": caseId},
    ).mappings().all()

    return {
        "reports": [dict(row) for row in reportRows],
        "agentRuns": [dict(row) for row in runRows],
    }

@router.get("/reports")
def getAllReports(
    db: Session = Depends(getDb),
    currentUser: User = Depends(getCurrentUser),
):
    agentRows = db.execute(
        text("""
            select
              ar.id,
              ar.case_id,
              ar.agent_name,
              ar.status,
              ar.result_summary,
              ar.result_payload,
              ar.created_at,
              c.case_number,
              c.title as case_title,
              cl.full_name as client_name
            from agent_runs ar
            join cases c on c.id = ar.case_id
            join clients cl on cl.id = c.client_id
            join case_users cu on cu.case_id = c.id
            where cu.user_id = :user_id
            order by ar.created_at desc
            limit 100
        """),
        {"user_id": str(currentUser.id)},
    ).mappings().all()

    reportRows = db.execute(
        text("""
            select
              rl.id,
              rl.case_id,
              rl.report_type,
              rl.title,
              rl.summary,
              rl.created_at,
              c.case_number,
              c.title as case_title,
              cl.full_name as client_name
            from report_logs rl
            join cases c on c.id = rl.case_id
            join clients cl on cl.id = c.client_id
            join case_users cu on cu.case_id = c.id
            where cu.user_id = :user_id
            order by rl.created_at desc
            limit 100
        """),
        {"user_id": str(currentUser.id)},
    ).mappings().all()

    return {
        "agentRuns": [dict(row) for row in agentRows],
        "reports": [dict(row) for row in reportRows],
    }