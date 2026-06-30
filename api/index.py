from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.auth import router as authRouter
from app.cases import router as casesRouter
from app.documents import router as documentsRouter
from app.rag import router as ragRouter
from app.actions import router as actionsRouter
from app.legal_ops import router as legalOpsRouter
from app.dashboard import router as dashboardRouter
from app.autopilot import router as autopilotRouter
from app.advanced_agents import router as advancedAgentsRouter
from app.calendar_sync import router as calendarSyncRouter
from app.intake import router as intakeRouter

app = FastAPI(title="DocketIQ API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://*.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(authRouter)
app.include_router(casesRouter)
app.include_router(documentsRouter)
app.include_router(ragRouter)
app.include_router(actionsRouter)
app.include_router(legalOpsRouter)
app.include_router(dashboardRouter)
app.include_router(autopilotRouter)
app.include_router(advancedAgentsRouter)
app.include_router(calendarSyncRouter)
app.include_router(intakeRouter)

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "DocketIQ API",
        "phase": "Final Phase"
    }

@app.get("/api/project")
def project():
    return {
        "name": "DocketIQ",
        "description": "Agentic legal operations platform for personal injury case workflows",
        "features": [
            "Google OAuth",
            "Supabase PostgreSQL",
            "Encrypted Google tokens",
            "Role-based users",
            "Gmail API ready",
            "Calendar API ready",
            "Document upload",
            "Gemini RAG",
            "LLM firewall",
            "Case-grounded chat"
        ]
    }