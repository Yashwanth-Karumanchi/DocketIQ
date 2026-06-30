from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "DocketIQ API",
        "phase": "Phase 1 Foundation"
    }

@app.get("/api/project")
def project():
    return {
        "name": "DocketIQ",
        "description": "Agentic legal operations platform for personal injury case workflows",
        "features": [
            "Google OAuth",
            "Case management",
            "Document RAG",
            "LLM firewall",
            "Gmail sending",
            "Calendar scheduling",
            "Attorney handoff reports"
        ]
    }