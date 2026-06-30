import requests
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.google_tokens import getGoogleAccessToken
from app.models import User

CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"

def createCalendarEvent(
    db: Session,
    currentUser: User,
    title: str,
    description: str,
    startTime: str,
    endTime: str,
    timeZone: str = "America/Denver",
    attendees: list[str] | None = None,
):
    accessToken = getGoogleAccessToken(db, str(currentUser.id))

    eventBody = {
        "summary": title,
        "description": description,
        "start": {
            "dateTime": startTime,
            "timeZone": timeZone,
        },
        "end": {
            "dateTime": endTime,
            "timeZone": timeZone,
        },
        "attendees": [{"email": email} for email in attendees or []],
    }

    response = requests.post(
        CALENDAR_EVENTS_URL,
        headers={
            "Authorization": f"Bearer {accessToken}",
            "Content-Type": "application/json",
        },
        json=eventBody,
        timeout=30,
    )

    if response.status_code not in [200, 201]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Calendar event creation failed",
                "googleStatus": response.status_code,
                "googleResponse": response.text,
            },
        )

    return response.json()