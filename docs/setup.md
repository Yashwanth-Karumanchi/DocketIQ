# DocketIQ Setup

## 1. Backend Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Run backend:

```bash
uvicorn api.index:app --reload --port 8000
```

Backend URL:

```txt
http://localhost:8000
```

Docs:

```txt
http://localhost:8000/docs
```

---

## 2. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend URL:

```txt
http://localhost:5173
```

---

## 3. Google Cloud Setup

Create an OAuth client:

```txt
Application type: Web application
```

Authorized JavaScript origins:

```txt
http://localhost:5173
http://localhost:8000
```

Authorized redirect URI:

```txt
http://localhost:8000/api/auth/google/callback
```

Enable APIs:

* Gmail API
* Google Calendar API

Add test users in Google OAuth consent screen if your app is in testing mode.

---

## 4. Environment Variables

Create `.env`:

```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DATABASE

APP_BASE_URL=http://localhost:8000
FRONTEND_BASE_URL=http://localhost:5173

JWT_SECRET=replace_with_secure_secret
SESSION_COOKIE_NAME=docketiq_session

GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/auth/google/callback

GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.1-flash-lite

ALLOWED_EMAILS=your_email@gmail.com,test_user@gmail.com
```

---

## 5. Database

Enable pgvector:

```sql
create extension if not exists vector;
```

After demo cases are created, allow all existing test users to see all cases:

```sql
insert into case_users (case_id, user_id, access_level)
select c.id, u.id, 'manager'
from cases c
cross join users u
where not exists (
  select 1
  from case_users cu
  where cu.case_id = c.id
    and cu.user_id = u.id
);
```

---

## 6. Restart

```bash
uvicorn api.index:app --reload --port 8000
```

```bash
cd frontend
npm run dev
```