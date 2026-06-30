from datetime import datetime, timezone
from urllib.parse import urlencode
import requests
from fastapi import APIRouter, Depends, Request, Response, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.config import ALLOWED_EMAILS

from app.config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    GOOGLE_SCOPES,
    FRONTEND_URL,
    APP_ENV,
)
from app.db import getDb
from app.models import User, UserGoogleToken
from app.security import createSessionToken, decodeSessionToken, encryptText
from app.access_bootstrap import grantAllowedUserAllCases

router = APIRouter(prefix="/api/auth", tags=["auth"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

@router.get("/google/start")
def googleStart():
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(params)}")

@router.get("/google/callback")
def googleCallback(code: str, response: Response, db: Session = Depends(getDb)):
    tokenResponse = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=20,
    )

    if tokenResponse.status_code != 200:
        raise HTTPException(status_code=400, detail="Google token exchange failed")

    tokenData = tokenResponse.json()
    accessToken = tokenData.get("access_token")
    refreshToken = tokenData.get("refresh_token")
    expiresIn = tokenData.get("expires_in", 3600)
    scopes = tokenData.get("scope", "")

    userInfoResponse = requests.get(
        GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {accessToken}"},
        timeout=20,
    )

    if userInfoResponse.status_code != 200:
        raise HTTPException(status_code=400, detail="Google userinfo failed")

    profile = userInfoResponse.json()

    googleSub = profile["sub"]
    email = profile["email"]
    if ALLOWED_EMAILS and email.lower() not in ALLOWED_EMAILS:
        raise HTTPException(
            status_code=403,
            detail="This Google account is not authorized to access DocketIQ."
        )
    fullName = profile.get("name")
    avatarUrl = profile.get("picture")

    user = db.execute(select(User).where(User.google_sub == googleSub)).scalar_one_or_none()

    if not user:
        user = User(
            google_sub=googleSub,
            email=email,
            full_name=fullName,
            avatar_url=avatarUrl,
            role="case_manager",
        )
        db.add(user)
        db.flush()
        grantAllowedUserAllCases(db, user)
    else:
        user.email = email
        user.full_name = fullName
        user.avatar_url = avatarUrl

    tokenRecord = db.execute(
        select(UserGoogleToken).where(UserGoogleToken.user_id == user.id)
    ).scalar_one_or_none()

    expiry = datetime.fromtimestamp(
        datetime.now(timezone.utc).timestamp() + expiresIn,
        timezone.utc,
    )

    if not tokenRecord:
        tokenRecord = UserGoogleToken(user_id=user.id)
        db.add(tokenRecord)

    tokenRecord.encrypted_access_token = encryptText(accessToken)

    if refreshToken:
        tokenRecord.encrypted_refresh_token = encryptText(refreshToken)

    tokenRecord.token_expiry = expiry
    tokenRecord.scopes = scopes

    db.commit()

    sessionToken = createSessionToken(str(user.id))

    redirect = RedirectResponse(f"{FRONTEND_URL}/dashboard")
    redirect.set_cookie(
        key="docketiq_session",
        value=sessionToken,
        httponly=True,
        secure=APP_ENV == "production",
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )

    return redirect

def getCurrentUser(request: Request, db: Session = Depends(getDb)) -> User:
    sessionToken = request.cookies.get("docketiq_session")

    if not sessionToken:
        raise HTTPException(status_code=401, detail="Not authenticated")

    userId = decodeSessionToken(sessionToken)

    if not userId:
        raise HTTPException(status_code=401, detail="Invalid session")

    user = db.get(User, userId)

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user

@router.get("/me")
def me(currentUser: User = Depends(getCurrentUser)):
    return {
        "id": str(currentUser.id),
        "email": currentUser.email,
        "fullName": currentUser.full_name,
        "avatarUrl": currentUser.avatar_url,
        "role": currentUser.role,
    }

@router.post("/logout")
def logout():
    response = Response(content='{"ok": true}', media_type="application/json")
    response.delete_cookie("docketiq_session")
    return response