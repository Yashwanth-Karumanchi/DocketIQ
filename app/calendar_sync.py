from datetime import datetime, timedelta, timezone
import requests
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.auth import getCurrentUser
from app.db import getDb
from app.models import User
from app.google_tokens import getGoogleAccessToken

router = APIRouter(prefix="/api/calendar", tags=["calendar"])

GOOGLE_CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


def toGoogleTime(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


@router.get("/upcoming")
def getUpcomingGoogleCalendarEvents(
    response: Response,
    db: Session = Depends(getDb),
    currentUser: User = Depends(getCurrentUser),
):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"

    accessToken = getGoogleAccessToken(db, str(currentUser.id))

    now = datetime.now(timezone.utc)
    timeMax = now + timedelta(days=30)

    googleResponse = requests.get(
        GOOGLE_CALENDAR_EVENTS_URL,
        headers={
            "Authorization": f"Bearer {accessToken}",
        },
        params={
            "timeMin": toGoogleTime(now),
            "timeMax": toGoogleTime(timeMax),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": 20,
            "showDeleted": "false",
        },
        timeout=20,
    )

    if googleResponse.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Could not sync Google Calendar events",
                "googleStatus": googleResponse.status_code,
                "googleResponse": googleResponse.text,
            },
        )

    data = googleResponse.json()
    events = []

    for item in data.get("items", []):
        if item.get("status") == "cancelled":
            continue

        start = item.get("start", {})
        end = item.get("end", {})

        events.append({
            "id": item.get("id"),
            "title": item.get("summary", "Untitled event"),
            "description": item.get("description", ""),
            "start_time": start.get("dateTime") or start.get("date"),
            "end_time": end.get("dateTime") or end.get("date"),
            "google_event_link": item.get("htmlLink"),
            "attendees": item.get("attendees", []),
            "source": "google_calendar",
        })

    return {
        "events": events,
        "syncedAt": datetime.now(timezone.utc).isoformat(),
    }