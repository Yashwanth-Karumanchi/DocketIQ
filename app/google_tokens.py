from datetime import datetime, timezone, timedelta
import requests
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
from app.security import decryptText, encryptText

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

def getGoogleAccessToken(db: Session, userId: str) -> str:
    row = db.execute(
        text("""
            select
              encrypted_access_token,
              encrypted_refresh_token,
              token_expiry
            from user_google_tokens
            where user_id = :user_id
            limit 1
        """),
        {"user_id": userId},
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=401, detail="Google account is not connected")

    accessToken = decryptText(row["encrypted_access_token"])
    refreshToken = decryptText(row["encrypted_refresh_token"])
    tokenExpiry = row["token_expiry"]

    now = datetime.now(timezone.utc)

    if tokenExpiry and tokenExpiry > now + timedelta(minutes=2) and accessToken:
        return accessToken

    if not refreshToken:
        raise HTTPException(
            status_code=401,
            detail="Google refresh token missing. Please log out and sign in again.",
        )

    response = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "refresh_token": refreshToken,
            "grant_type": "refresh_token",
        },
        timeout=20,
    )

    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Could not refresh Google access token")

    tokenData = response.json()
    newAccessToken = tokenData.get("access_token")
    expiresIn = tokenData.get("expires_in", 3600)

    if not newAccessToken:
        raise HTTPException(status_code=401, detail="Google did not return an access token")

    newExpiry = now + timedelta(seconds=expiresIn)

    db.execute(
        text("""
            update user_google_tokens
            set
              encrypted_access_token = :encrypted_access_token,
              token_expiry = :token_expiry,
              updated_at = now()
            where user_id = :user_id
        """),
        {
            "user_id": userId,
            "encrypted_access_token": encryptText(newAccessToken),
            "token_expiry": newExpiry,
        },
    )

    return newAccessToken