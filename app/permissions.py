from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models import User

def verifyCaseAccess(db: Session, currentUser: User, caseId: str):
    row = db.execute(
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

    if not row:
        raise HTTPException(status_code=403, detail="You do not have access to this case")