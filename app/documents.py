import json
from io import BytesIO
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session
from sqlalchemy import text
from pypdf import PdfReader

from app.auth import getCurrentUser
from app.db import getDb
from app.models import User
from app.permissions import verifyCaseAccess
from app.llm import createEmbedding, toPgVector
from app.config import MAX_UPLOAD_MB

router = APIRouter(prefix="/api/documents", tags=["documents"])

def extractPdfText(fileBytes: bytes) -> str:
    reader = PdfReader(BytesIO(fileBytes))
    pages = []

    for index, page in enumerate(reader.pages):
        pageText = page.extract_text() or ""
        pages.append(f"\n\n--- Page {index + 1} ---\n{pageText}")

    return "\n".join(pages).strip()

def chunkText(textValue: str, chunkSize: int = 1800, overlap: int = 250) -> list[str]:
    cleaned = " ".join(textValue.split())

    if len(cleaned) <= chunkSize:
        return [cleaned]

    chunks = []
    start = 0

    while start < len(cleaned):
        end = start + chunkSize
        chunk = cleaned[start:end].strip()

        if chunk:
            chunks.append(chunk)

        start = end - overlap

    return chunks

@router.get("/cases/{caseId}")
def listDocuments(
    caseId: str,
    db: Session = Depends(getDb),
    currentUser: User = Depends(getCurrentUser),
):
    verifyCaseAccess(db, currentUser, caseId)

    rows = db.execute(
        text("""
            select id, file_name, mime_type, text_char_count, status, created_at
            from documents
            where case_id = :case_id
            order by created_at desc
        """),
        {"case_id": caseId},
    ).mappings().all()

    return {"documents": [dict(row) for row in rows]}

@router.post("/cases/{caseId}/upload")
async def uploadDocument(
    caseId: str,
    file: UploadFile = File(...),
    db: Session = Depends(getDb),
    currentUser: User = Depends(getCurrentUser),
):
    verifyCaseAccess(db, currentUser, caseId)

    fileBytes = await file.read()
    maxBytes = MAX_UPLOAD_MB * 1024 * 1024

    if len(fileBytes) > maxBytes:
        raise HTTPException(status_code=413, detail=f"File is larger than {MAX_UPLOAD_MB} MB")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported in Phase 4")

    extractedText = extractPdfText(fileBytes)

    if len(extractedText.strip()) < 50:
        raise HTTPException(
            status_code=400,
            detail="Could not extract enough text from this PDF. Scanned OCR support will be added later.",
        )

    chunks = chunkText(extractedText)

    document = db.execute(
        text("""
            insert into documents (
              case_id,
              uploaded_by,
              file_name,
              mime_type,
              text_char_count,
              status
            )
            values (
              :case_id,
              :uploaded_by,
              :file_name,
              :mime_type,
              :text_char_count,
              'Processed'
            )
            returning id
        """),
        {
            "case_id": caseId,
            "uploaded_by": str(currentUser.id),
            "file_name": file.filename,
            "mime_type": file.content_type,
            "text_char_count": len(extractedText),
        },
    ).mappings().first()

    documentId = str(document["id"])

    for index, chunk in enumerate(chunks):
        embedding = createEmbedding(chunk)
        vectorValue = toPgVector(embedding)

        db.execute(
            text("""
                insert into document_chunks (
                  case_id,
                  document_id,
                  chunk_index,
                  content,
                  embedding
                )
                values (
                  :case_id,
                  :document_id,
                  :chunk_index,
                  :content,
                  cast(:embedding as halfvec)
                )
            """),
            {
                "case_id": caseId,
                "document_id": documentId,
                "chunk_index": index,
                "content": chunk,
                "embedding": vectorValue,
            },
        )

    db.execute(
        text("""
            insert into audit_logs (user_id, action, entity_type, entity_id, details)
            values (:user_id, 'document_uploaded', 'document', :document_id, cast(:details as jsonb))
        """),
        {
            "user_id": str(currentUser.id),
            "document_id": documentId,
            "details": json.dumps({
                "caseId": caseId,
                "fileName": file.filename,
                "chunks": len(chunks),
            }),
        },
    )

    db.commit()

    return {
        "documentId": documentId,
        "fileName": file.filename,
        "chunks": len(chunks),
        "textChars": len(extractedText),
        "message": "Document processed and embedded"
    }