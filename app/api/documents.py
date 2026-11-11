from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
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
from app.models.extraction import DocumentExtraction


from sqlalchemy import select

from app.models.document import Document
from app.schemas.financial import PayslipExtractionResponse
from app.services.pdf_extraction import extract_pdf_text
from app.services.payslip_extraction import extract_payslip_data
from app.schemas.bank_statement import (
    BankStatementExtraction,
    BankStatementExtractionResponse,
)
from app.services.bank_statement_extraction import (
    extract_bank_statement_data,
)

import logging

logger = logging.getLogger(__name__)

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
    
       
    
@router.post(
    "/{application_id}/documents/{document_id}/analyze-payslip",
    response_model=PayslipExtractionResponse,
)
def analyze_payslip(
    application_id: int,
    document_id: int,
    db: Session = Depends(get_db),
):
    # 1. Find document
    statement = select(Document).where(
        Document.id == document_id,
        Document.application_id == application_id,
    )

    document = db.scalar(statement)

    if not document:
        raise HTTPException(404, "Document not found")

    if document.document_type != "payslip":
        raise HTTPException(400, "Document is not a payslip")

    # 2. Check whether extraction already exists
    statement = select(DocumentExtraction).where(
        DocumentExtraction.document_id == document_id,
        DocumentExtraction.extraction_type == "payslip",
    )

    existing_extraction = db.scalar(statement)

    if existing_extraction:
        return PayslipExtractionResponse(
            document_id=document.id,
            application_id=document.application_id,
            original_filename=document.original_filename,
            **existing_extraction.extracted_data,
        )

    # 3. Extract PDF text
    pdf_result = extract_pdf_text(document.storage_path)

    if not pdf_result["has_extractable_text"]:
        raise HTTPException(
            422,
            "No readable text found in PDF",
        )

    # 4. Extract financial information using LLM
    try:
        result = extract_payslip_data(
            pdf_result["extracted_text"]
        )

        extracted_data = result.model_dump(mode="json")

    except Exception as exc:
        logger.exception("Payslip extraction failed")

        raise HTTPException(
            502,
            "Payslip AI extraction failed",
        ) from exc

    # 5. Save extraction result in database
    extraction = DocumentExtraction(
        document_id=document.id,
        extraction_type="payslip",
        extracted_data=extracted_data,
    )

    db.add(extraction)
    db.commit()
    db.refresh(extraction)

    # 6. Return extracted information
    return PayslipExtractionResponse(
        document_id=document.id,
        application_id=document.application_id,
        original_filename=document.original_filename,
        **extracted_data,
    )


@router.post(
    "/{application_id}/documents/{document_id}/analyze-bank-statement",
    response_model=BankStatementExtractionResponse,
)
def analyze_bank_statement(
    application_id: int,
    document_id: int,
    force_refresh: bool = Query(
        default=False,
        description=(
            "Re-extract and replace the saved bank-statement extraction "
            "without deleting the uploaded document."
        ),
    ),
    db: Session = Depends(get_db),
):
    application = db.get(LoanApplication, application_id)

    if not application:
        raise HTTPException(404, "Loan application not found")

    statement = select(Document).where(
        Document.id == document_id,
        Document.application_id == application_id,
    )
    document = db.scalar(statement)

    if not document:
        raise HTTPException(404, "Document not found")

    if document.document_type != "bank_statement":
        raise HTTPException(400, "Document is not a bank statement")

    statement = select(DocumentExtraction).where(
        DocumentExtraction.document_id == document_id,
        DocumentExtraction.extraction_type == "bank_statement",
    )
    existing_extraction = db.scalar(statement)

    is_legacy_extraction = (
        existing_extraction is not None
        and (
            "statement_total_credits"
            not in existing_extraction.extracted_data
            or "statement_total_debits"
            not in existing_extraction.extracted_data
        )
    )
    if existing_extraction and not force_refresh and not is_legacy_extraction:
        return BankStatementExtractionResponse(
            document_id=document.id,
            application_id=document.application_id,
            original_filename=document.original_filename,
            **existing_extraction.extracted_data,
        )

    try:
        pdf_result = extract_pdf_text(document.storage_path)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(
            422,
            "Unable to read text from the PDF document",
        ) from exc

    if not pdf_result["has_extractable_text"]:
        raise HTTPException(422, "No readable text found in PDF")

    try:
        result = extract_bank_statement_data(pdf_result["extracted_text"])
        validated_result = BankStatementExtraction.model_validate(result)
        extracted_data = validated_result.model_dump(mode="json")
    except Exception as exc:
        logger.error(
            "Bank statement extraction failed (%s)",
            type(exc).__name__,
            stack_info=True,
        )
        raise HTTPException(
            502,
            "Bank statement AI extraction failed",
        ) from exc

    if existing_extraction:
        existing_extraction.extracted_data = extracted_data
    else:
        extraction = DocumentExtraction(
            document_id=document.id,
            extraction_type="bank_statement",
            extracted_data=extracted_data,
        )
        db.add(extraction)
    db.commit()
    if existing_extraction:
        db.refresh(existing_extraction)
    else:
        db.refresh(extraction)

    return BankStatementExtractionResponse(
        document_id=document.id,
        application_id=document.application_id,
        original_filename=document.original_filename,
        **extracted_data,
    )
    
