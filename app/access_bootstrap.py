from sqlalchemy.orm import Session
from sqlalchemy import text

from app.config import ALLOWED_EMAILS
from app.models import User


def grantAllowedUserAllCases(db: Session, currentUser: User):
    userEmail = (currentUser.email or "").lower()

    if ALLOWED_EMAILS and userEmail not in ALLOWED_EMAILS:
        return

    db.execute(
        text("""
            insert into case_users (case_id, user_id, access_level)
            select c.id, :user_id, 'manager'
            from cases c
            where not exists (
                select 1
                from case_users cu
                where cu.case_id = c.id
                  and cu.user_id = :user_id
            )
        """),
        {"user_id": str(currentUser.id)},
    )