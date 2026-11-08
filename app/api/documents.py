from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from pathlib import Path
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.application import LoanApplication
from app.models.document import Document
from app.schemas.document import DocumentResponse
from app.services.document_service import save_document
from sqlalchemy import select

router = APIRouter(
    prefix="/applications",
    tags=["Documents"],
)


ALLOWED_DOCUMENT_TYPES = {
    "payslip",
    "bank_statement",
    "existing_loan_statement",
}


@router.post(
    "/{application_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    application_id: int,
    document_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    # 1. Verify application exists
    application = db.get(LoanApplication, application_id)

    if not application:
        raise HTTPException(
            status_code=404,
            detail="Loan application not found",
        )

    # 2. Validate document type
    if document_type not in ALLOWED_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Invalid document type",
        )

    # 3. Save PDF
    try:
        file_data = await save_document(file, application_id)

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    finally:
        await file.close()

    # 4. Save document metadata in database
    document = Document(
        application_id=application_id,
        document_type=document_type,
        **file_data,
    )

    try:
        db.add(document)
        db.commit()
        db.refresh(document)

    except Exception:
        db.rollback()

        Path(file_data["storage_path"]).unlink(missing_ok=True)

        raise HTTPException(
            status_code=500,
            detail="Failed to save document information",
        )

    return document


@router.get(
    "/{application_id}/documents",
    response_model=list[DocumentResponse],
)
def get_documents(
    application_id: int,
    db: Session = Depends(get_db),
):
    application = db.get(LoanApplication, application_id)

    if not application:
        raise HTTPException(
            status_code=404,
            detail="Loan application not found",
        )

    statement = (
        select(Document)
        .where(Document.application_id == application_id)
        .order_by(Document.created_at.desc())
    )

    return db.scalars(statement).all()