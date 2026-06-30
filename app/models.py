from sqlalchemy import Column, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.db import Base
import uuid

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    google_sub = Column(Text, unique=True, nullable=False)
    email = Column(Text, unique=True, nullable=False)
    full_name = Column(Text)
    avatar_url = Column(Text)
    role = Column(Text, nullable=False, default="case_manager")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

class UserGoogleToken(Base):
    __tablename__ = "user_google_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    encrypted_access_token = Column(Text)
    encrypted_refresh_token = Column(Text)
    token_expiry = Column(DateTime(timezone=True))
    scopes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    action = Column(Text, nullable=False)
    entity_type = Column(Text)
    entity_id = Column(Text)
    details = Column(JSONB, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Client(Base):
    __tablename__ = "clients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name = Column(Text, nullable=False)
    email = Column(Text)
    phone = Column(Text)
    preferred_language = Column(Text, default="English")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Case(Base):
    __tablename__ = "cases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    case_number = Column(Text, unique=True, nullable=False)
    title = Column(Text, nullable=False)
    case_type = Column(Text, nullable=False, default="Personal Injury")
    incident_date = Column(DateTime)
    status = Column(Text, nullable=False, default="Intake")
    priority = Column(Text, nullable=False, default="Medium")
    insurance_company = Column(Text)
    claim_number = Column(Text)
    summary = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class CaseUser(Base):
    __tablename__ = "case_users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    access_level = Column(Text, nullable=False, default="manager")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class CaseNote(Base):
    __tablename__ = "case_notes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    note = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class CaseTask(Base):
    __tablename__ = "case_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text)
    status = Column(Text, nullable=False, default="Open")
    priority = Column(Text, nullable=False, default="Medium")
    due_date = Column(DateTime)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class CaseTimelineEvent(Base):
    __tablename__ = "case_timeline_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    event_date = Column(DateTime, nullable=False)
    event_type = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text)
    source = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())