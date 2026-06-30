from typing import Literal
from pydantic import BaseModel
from app.llm import generateText, parseJsonObject

class FirewallResult(BaseModel):
    decision: Literal[
        "allow",
        "allow_with_limits",
        "ask_clarifying",
        "refuse",
        "require_confirmation"
    ]
    riskLevel: Literal["low", "medium", "high"]
    reason: str
    allowedTools: list[str]

def runFirewall(userMessage: str) -> FirewallResult:
    message = userMessage.lower().strip()

    externalActionWords = [
        "send email",
        "send mail",
        "email the",
        "mail the",
        "schedule",
        "calendar",
        "invite",
        "create meeting",
        "book meeting",
        "set up meeting",
        "set up a call",
    ]

    unsafeWords = [
        "fake",
        "fabricate",
        "exaggerate",
        "lie",
        "alter evidence",
        "make injuries sound worse",
        "hide evidence",
    ]

    legalAdviceWords = [
        "should we sue",
        "should i sue",
        "should they sue",
        "should we settle",
        "accept settlement",
        "legal strategy",
        "who is liable",
        "is he liable",
        "is she liable",
        "case value",
        "how much is this worth",
    ]

    if any(word in message for word in unsafeWords):
        return FirewallResult(
            decision="refuse",
            riskLevel="high",
            reason="The request appears to involve fabrication, exaggeration, or misleading case information.",
            allowedTools=["none"],
        )

    if any(word in message for word in legalAdviceWords):
        return FirewallResult(
            decision="refuse",
            riskLevel="high",
            reason="The request asks for legal advice or legal strategy, which DocketIQ cannot provide.",
            allowedTools=["none"],
        )

    if any(word in message for word in externalActionWords):
        return FirewallResult(
            decision="require_confirmation",
            riskLevel="medium",
            reason="The request requires an external action such as sending an email or creating a calendar event.",
            allowedTools=["email_draft", "email_send", "calendar_create"],
        )

    prompt = f"""
You are the DocketIQ LLM firewall for a personal-injury legal operations platform.

The frontend always sends the selected case id. So if the user says:
- this case
- current case
- selected case
- summarize this
- summarize this case
- what is missing
- what happened
- what should the case manager do next

Treat that as referring to the selected case. Do NOT ask which file unless the user specifically asks to summarize a particular uploaded file but does not name it.

DocketIQ can help with:
- Case summaries
- Case status summaries
- Intake information
- Missing document tracking
- Treatment timelines
- Insurance and claim information
- Calendar and communication status
- Drafting operational emails
- Scheduling operational calendar events
- Attorney handoff summaries
- Case-status questions grounded in available case data

DocketIQ must refuse:
- Legal advice, including whether someone should sue, settle, or accept a legal strategy
- Medical advice or diagnosis
- Requests to exaggerate injuries, fabricate records, alter evidence, or mislead insurers
- Anything unrelated to legal operations
- Answers that would require inventing facts not in the case record

Decision meanings:
- allow: safe to answer normally
- allow_with_limits: answer, but include limitation that this is operational info only
- ask_clarifying: only use this when the user's request cannot be resolved from the selected case context
- refuse: unsafe or outside scope
- require_confirmation: user asks to send email, create calendar invite, or take external action

Allowed tools:
- rag_search
- document_summary
- email_draft
- email_send
- calendar_create
- report_generate
- none

Return ONLY valid JSON with this exact shape:
{{
  "decision": "allow",
  "riskLevel": "low",
  "reason": "short reason",
  "allowedTools": ["rag_search"]
}}

User message:
{userMessage}
"""

    try:
        raw = generateText(prompt)
        data = parseJsonObject(raw)

        return FirewallResult(
            decision=data.get("decision", "allow"),
            riskLevel=data.get("riskLevel", "low"),
            reason=data.get("reason", "Safe legal operations request for selected case."),
            allowedTools=data.get("allowedTools", ["rag_search"]),
        )
    except Exception:
        return FirewallResult(
            decision="allow_with_limits",
            riskLevel="medium",
            reason="Firewall fallback allowed this as an operational selected-case request.",
            allowedTools=["rag_search"],
        )