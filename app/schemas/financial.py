from decimal import Decimal

from pydantic import BaseModel, Field


class PayslipExtraction(BaseModel):
    employee_name: str | None = None
    employer_name: str | None = None
    pay_period: str | None = None

    currency: str | None = None

    gross_salary: Decimal | None = Field(
        default=None,
        description="Gross salary before deductions",
    )

    total_deductions: Decimal | None = None

    net_salary: Decimal | None = Field(
        default=None,
        description="Take-home salary after deductions",
    )

    evidence: list[str] = Field(
        default_factory=list,
        description="Short exact excerpts supporting extracted values",
    )

    missing_fields: list[str] = Field(
        default_factory=list,
        description="Fields that could not be found in the document",
    )
    
    
    
class PayslipExtractionResponse(PayslipExtraction):
    document_id: int
    application_id: int
    original_filename: str
    
    
    
    
    
