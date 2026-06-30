import base64
from email.message import EmailMessage
import requests
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.google_tokens import getGoogleAccessToken
from app.models import User

GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

def createRawEmail(
    fromEmail: str,
    toEmail: str,
    subject: str,
    body: str,
    cc: str | None = None,
    bcc: str | None = None,
) -> str:
    message = EmailMessage()
    message["To"] = toEmail
    message["From"] = fromEmail
    message["Subject"] = subject

    if cc:
        message["Cc"] = cc

    if bcc:
        message["Bcc"] = bcc

    message.set_content(body)

    rawBytes = message.as_bytes()
    return base64.urlsafe_b64encode(rawBytes).decode()

def sendGmailEmail(
    db: Session,
    currentUser: User,
    toEmail: str,
    subject: str,
    body: str,
    cc: str | None = None,
    bcc: str | None = None,
):
    accessToken = getGoogleAccessToken(db, str(currentUser.id))

    rawEmail = createRawEmail(
        fromEmail=currentUser.email,
        toEmail=toEmail,
        subject=subject,
        body=body,
        cc=cc,
        bcc=bcc,
    )

    response = requests.post(
        GMAIL_SEND_URL,
        headers={
            "Authorization": f"Bearer {accessToken}",
            "Content-Type": "application/json",
        },
        json={"raw": rawEmail},
        timeout=30,
    )

    if response.status_code not in [200, 201]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Gmail send failed",
                "googleStatus": response.status_code,
                "googleResponse": response.text,
            },
        )

    return response.json()