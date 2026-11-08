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
from app.schemas.document import (
    ChecklistItem,
    DocumentChecklistResponse,
)
from app.services.pdf_extraction import extract_pdf_text

from app.schemas.document import DocumentExtractionResponse

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






@router.get(
    "/{application_id}/documents/checklist",
    response_model=DocumentChecklistResponse,
)
def get_document_checklist(
    application_id: int,
    db: Session = Depends(get_db),
):
    # Check whether application exists
    application = db.get(LoanApplication, application_id)

    if not application:
        raise HTTPException(
            status_code=404,
            detail="Loan application not found",
        )

    # Fetch uploaded documents
    statement = select(Document).where(
        Document.application_id == application_id
    )

    documents = db.scalars(statement).all()

    # Define document requirements
    requirements = [
        ("payslip", "Payslips (last 3 months)", True),
        ("bank_statement", "Bank statements (last 6 months)", True),
        ("existing_loan_statement", "Existing loan statements", False),
    ]

    items = []

    for document_type, label, required in requirements:
        count = sum(
            1 for doc in documents
            if doc.document_type == document_type
        )

        items.append(
            ChecklistItem(
                document_type=document_type,
                label=label,
                required=required,
                uploaded=count > 0,
                document_count=count,
            )
        )

    ready = all(
        item.uploaded
        for item in items
        if item.required
    )

    return DocumentChecklistResponse(
        application_id=application_id,
        ready_for_analysis=ready,
        items=items,
    )
    
    
   
   
@router.post(
    "/{application_id}/documents/{document_id}/extract",
    response_model=DocumentExtractionResponse,
)
def extract_document(
    application_id: int,
    document_id: int,
    db: Session = Depends(get_db),
):
    # Find the document and verify its application
    statement = select(Document).where(
        Document.id == document_id,
        Document.application_id == application_id,
    )

    document = db.scalar(statement)

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    try:
        result = extract_pdf_text(document.storage_path)
        print(f"Extracted text from document {document_id}: {result['extracted_text']}")  # Log first 100 chars

    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="PDF file not found in storage",
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    return DocumentExtractionResponse(
        document_id=document.id,
        application_id=document.application_id,
        original_filename=document.original_filename,
        **result,
    )
    
       
    
    