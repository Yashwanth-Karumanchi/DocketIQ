from typing import Literal
from pydantic import BaseModel

from app.llm import generateText, parseJsonObject


class FirewallResult(BaseModel):
    decision: Literal[
        "allow",
        "allow_with_limits",
        "ask_clarifying",
        "refuse",
        "require_confirmation",
    ]
    riskLevel: Literal["low", "medium", "high"]
    reason: str
    allowedTools: list[str]


def hasAny(message: str, words: list[str]) -> bool:
    return any(word in message for word in words)


def runFirewall(userMessage: str) -> FirewallResult:
    message = userMessage.lower().strip()

    dangerousDataWords = [
        "delete all",
        "remove all",
        "drop table",
        "truncate",
        "wipe database",
        "delete database",
        "delete every",
        "delete client",
        "delete case",
        "remove client",
        "remove case",
        "change user",
        "change permission",
        "make admin",
        "delete audit",
        "remove audit",
        "raw sql",
        "run sql",
    ]

    if hasAny(message, dangerousDataWords):
        return FirewallResult(
            decision="refuse",
            riskLevel="high",
            reason="This request attempts a destructive or administrative database operation that is not allowed through chat.",
            allowedTools=[],
        )

    dbActionWords = [
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
        "connect with",
        "disconnect",
        "remove connection",
        "delete connection",
        "add communication suggestion",
        "create communication suggestion",
    ]

    if hasAny(message, dbActionWords):
        return FirewallResult(
            decision="require_confirmation",
            riskLevel="medium",
            reason="This request changes structured case data and must be prepared as a pending action for user confirmation.",
            allowedTools=["database_action"],
        )

    externalActionWords = [
        "send email",
        "email the",
        "send mail",
        "gmail",
        "schedule",
        "calendar",
        "create event",
        "book meeting",
        "invite",
        "appointment",
        "consultation",
    ]

    if hasAny(message, externalActionWords):
        return FirewallResult(
            decision="require_confirmation",
            riskLevel="medium",
            reason="This request may trigger an external Gmail or Google Calendar action and requires confirmation.",
            allowedTools=["gmail", "calendar"],
        )

    unsafeWords = [
        "fake evidence",
        "forge",
        "fabricate",
        "backdate",
        "lie",
        "hide evidence",
        "delete evidence",
        "destroy evidence",
        "misrepresent",
    ]

    if hasAny(message, unsafeWords):
        return FirewallResult(
            decision="refuse",
            riskLevel="high",
            reason="This request could involve fabrication, concealment, or misuse of case information.",
            allowedTools=[],
        )

    legalAdviceWords = [
        "should we sue",
        "should i sue",
        "is this malpractice",
        "what settlement",
        "settlement amount",
        "accept liability",
        "who is liable",
        "legal strategy",
        "file a lawsuit",
    ]

    if hasAny(message, legalAdviceWords):
        return FirewallResult(
            decision="refuse",
            riskLevel="high",
            reason="This asks for legal advice or legal strategy. I can only help with legal operations tasks.",
            allowedTools=[],
        )

    prompt = f"""
You are DocketIQ's safety firewall.

Classify this legal-operations assistant request.

Important:
- The assistant may summarize case data, tasks, documents, timelines, reports, connected cases, and operational next steps.
- The assistant may prepare pending Gmail, Calendar, or database actions only when the user confirms later.
- The assistant must not provide legal advice, medical advice, settlement advice, liability decisions, or fabricated facts.
- The assistant must not execute destructive database operations.
- Questions about "this case", "current case", or "selected case" are allowed because the app already provides selected-case context.

Return ONLY valid JSON.

JSON shape:
{{
  "decision": "allow",
  "riskLevel": "low",
  "reason": "short reason",
  "allowedTools": []
}}

Allowed decision values:
allow
allow_with_limits
ask_clarifying
refuse
require_confirmation

User request:
{userMessage}
"""

    try:
        raw = generateText(prompt)
        data = parseJsonObject(raw)

        return FirewallResult(
            decision=data.get("decision", "allow"),
            riskLevel=data.get("riskLevel", "low"),
            reason=data.get("reason", "Allowed legal-operations request."),
            allowedTools=data.get("allowedTools", []),
        )
    except Exception:
        return FirewallResult(
            decision="allow",
            riskLevel="low",
            reason="Allowed by fallback legal-operations policy.",
            allowedTools=[],
        )