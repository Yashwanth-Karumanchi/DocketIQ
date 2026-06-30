# DocketIQ — Agentic Legal Ops AI

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-Frontend-61DAFB?logo=react&logoColor=0f172a)
![TypeScript](https://img.shields.io/badge/TypeScript-UI-3178C6?logo=typescript&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-Build-646CFF?logo=vite&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Database-4169E1?logo=postgresql&logoColor=white)
![Supabase](https://img.shields.io/badge/Supabase-Live_DB-3FCF8E?logo=supabase&logoColor=white)
![pgvector](https://img.shields.io/badge/pgvector-RAG-0F172A)
![Google OAuth](https://img.shields.io/badge/Google_OAuth-Login-4285F4?logo=google&logoColor=white)
![Gmail API](https://img.shields.io/badge/Gmail_API-Live-EA4335?logo=gmail&logoColor=white)
![Google Calendar](https://img.shields.io/badge/Google_Calendar-Live-4285F4?logo=googlecalendar&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini-LLM-8E75B2?logo=googlegemini&logoColor=white)

DocketIQ is a secure, agentic legal operations AI platform for managing case intake, documents, missing items, timelines, client communications, calendar scheduling, and attorney-ready handoff reports.

It is built as a production-style proof-of-skill project using FastAPI, React, PostgreSQL, pgvector, Google OAuth, Gmail API, Google Calendar API, and Gemini.

---

## What It Does

DocketIQ helps a legal operations team:

- Sign in with Google
- View case portfolio metrics
- Search and filter cases
- Create new cases through an Intake Agent
- Upload and analyze case PDFs
- Track missing documents
- Generate case timelines
- Run legal-ops agents
- Draft client follow-up emails
- Send Gmail messages only after user confirmation
- Create Google Calendar events only after user confirmation
- Generate attorney handoff reports
- Ask dashboard-level or case-specific AI questions

---

## Main Features

### Dashboard

- Active case count
- High-priority case count
- Open task count
- Pending action count
- Document count
- Clickable stat filters
- Dynamic search
- Operational queue
- Live calendar preview

### Case Workspace

Each case has:

- Case overview
- Missing items
- Uploaded documents
- Timeline
- Agent reports
- Communication Autopilot
- Case relationship graph
- Report history
- Floating AI assistant

### AI Agents

- Intake Agent
- Missing Items Agent
- Timeline Agent
- Case Readiness Agent
- Contradiction Agent
- Next Best Action Agent
- Case Relationship Agent
- Communication Autopilot
- Handoff Report Generator

### AI Chat

The chat works in two modes:

- No case selected: answers dashboard-level questions
- Case selected: answers using that case's records, tasks, timeline, documents, relationships, and memory

External actions always require confirmation.

---

## Quick Start

### Backend

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn api.index:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open:

```txt
http://localhost:5173
```

API docs:

```txt
http://localhost:8000/docs
```

---

## Environment Variables

Create `.env` in the root folder.

```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DATABASE

APP_BASE_URL=http://localhost:8000
FRONTEND_BASE_URL=http://localhost:5173

JWT_SECRET=replace_with_secure_secret
SESSION_COOKIE_NAME=docketiq_session

GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/auth/google/callback

GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.1-flash-lite

ALLOWED_EMAILS=your_email@gmail.com,test_user@gmail.com
```

Google scopes used:

```txt
openid
email
profile
https://www.googleapis.com/auth/gmail.send
https://www.googleapis.com/auth/calendar.events
https://www.googleapis.com/auth/calendar.events.readonly
```

---

## How To Use

1. Log in with an allowed Google account.
2. Use Dashboard to search, filter, and open cases.
3. Use New Case to create a case through the Intake Agent.
4. Open a case workspace.
5. Upload case PDFs.
6. Run Missing Items, Timeline, Readiness, Contradictions, Next Best Action, or Relationships.
7. Ask the chat questions about the case.
8. Use Communication Autopilot to generate follow-up suggestions.
9. Convert suggestions to pending emails.
10. Confirm Gmail or Calendar actions before execution.
11. Review generated reports in Reports.

---

## Safety

DocketIQ is an operational assistant, not a legal-advice engine.

It does not:

* Give legal advice
* Give medical advice
* Decide liability
* Recommend settlement
* Fabricate facts
* Exaggerate injuries
* Send emails without confirmation
* Create calendar events without confirmation

---

## Docs

More details:

* [`docs/SETUP.md`](docs/SETUP.md)
* [`docs/TESTING.md`](docs/TESTING.md)
* [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md)