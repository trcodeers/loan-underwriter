from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.application import LoanApplication
from app.schemas.application import ApplicationCreate
from app.schemas.application import ApplicationUpdate

from sqlalchemy import select
from fastapi import HTTPException

from app.schemas.application import ApplicationResponse

from app.schemas.verification import FinancialVerificationResponse
from app.models.financial_analysis import FinancialAnalysis
from app.schemas.financial_analysis import FinancialAnalysisResponse
from app.services.financial_verification import (
    FinancialVerificationDataUnavailable,
    verify_application_finances,
)

router = APIRouter(
    prefix="/applications",
    tags=["Applications"],
)


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_application(
    payload: ApplicationCreate,
    db: Session = Depends(get_db),
):
    application = LoanApplication(**payload.model_dump())

    db.add(application)
    db.commit()
    db.refresh(application)

    return application


@router.get("/", response_model=list[ApplicationResponse])
def get_applications(db: Session = Depends(get_db)):

    statement = (
        select(LoanApplication)
        .order_by(LoanApplication.created_at.desc())
    )

    applications = db.scalars(statement).all()

    return applications



@router.get("/{application_id}", response_model=ApplicationResponse)
def get_application(
    application_id: int,
    db: Session = Depends(get_db),
):

    application = db.get(LoanApplication, application_id)

    if not application:
        raise HTTPException(
            status_code=404,
            detail="Loan application not found",
        )

    return application


@router.get(
    "/{application_id}/financial-analyses/latest",
    response_model=FinancialAnalysisResponse,
)
def get_latest_financial_analysis(
    application_id: int,
    db: Session = Depends(get_db),
):
    application = db.get(LoanApplication, application_id)
    if not application:
        raise HTTPException(
            status_code=404,
            detail="Loan application not found",
        )

    analysis = db.scalar(
        select(FinancialAnalysis)
        .where(FinancialAnalysis.application_id == application_id)
        .order_by(
            FinancialAnalysis.created_at.desc(),
            FinancialAnalysis.id.desc(),
        )
        .limit(1)
    )
    if not analysis:
        raise HTTPException(
            status_code=404,
            detail="No financial analysis found for this application",
        )

    return FinancialAnalysisResponse(
        analysis_id=analysis.id,
        application_id=analysis.application_id,
        source_document_ids=analysis.source_document_ids,
        calculation_inputs=analysis.calculation_inputs,
        calculation_results=analysis.calculation_results,
        calculation_version=analysis.calculation_version,
        created_at=analysis.created_at,
    )


@router.post(
    "/{application_id}/verify-finances",
    response_model=FinancialVerificationResponse,
)
def verify_finances(
    application_id: int,
    db: Session = Depends(get_db),
):
    application = db.get(LoanApplication, application_id)
    if not application:
        raise HTTPException(
            status_code=404,
            detail="Loan application not found",
        )

    try:
        return verify_application_finances(db, application_id)
    except FinancialVerificationDataUnavailable as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc



@router.patch("/{application_id}", response_model=ApplicationResponse)
def update_application(
    application_id: int,
    payload: ApplicationUpdate,
    db: Session = Depends(get_db),
):
    application = db.get(LoanApplication, application_id)

    if not application:
        raise HTTPException(
            status_code=404,
            detail="Loan application not found",
        )

    update_data = payload.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(application, field, value)

    db.commit()
    db.refresh(application)

    return application


@router.delete(
    "/{application_id}",
    status_code=204,
)
def delete_application(
    application_id: int,
    db: Session = Depends(get_db),
):
    application = db.get(LoanApplication, application_id)

    if not application:
        raise HTTPException(
            status_code=404,
            detail="Loan application not found",
        )

    db.delete(application)
    db.commit()

    return Response(status_code=204)