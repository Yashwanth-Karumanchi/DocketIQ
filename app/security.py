from datetime import datetime, timedelta, timezone
from typing import Optional
from cryptography.fernet import Fernet
from jose import jwt, JWTError
from app.config import JWT_SECRET, TOKEN_ENCRYPTION_KEY

JWT_ALGORITHM = "HS256"

fernet = Fernet(TOKEN_ENCRYPTION_KEY.encode())

def encryptText(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return fernet.encrypt(value.encode()).decode()

def decryptText(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return fernet.decrypt(value.encode()).decode()

def createSessionToken(userId: str) -> str:
    payload = {
        "sub": userId,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decodeSessionToken(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None