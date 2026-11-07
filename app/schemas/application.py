from decimal import Decimal

from pydantic import BaseModel, Field


class ApplicationCreate(BaseModel):
    applicant_name: str = Field(min_length=2, max_length=120)

    requested_loan_amount: Decimal = Field(gt=0)

    loan_purpose: str = Field(min_length=2, max_length=255)
    
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class ApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    applicant_name: str
    requested_loan_amount: Decimal
    loan_purpose: str
    status: str
    created_at: datetime
    
class ApplicationUpdate(BaseModel):
    applicant_name: str | None = Field(
        default=None, min_length=2, max_length=120
    )

    requested_loan_amount: Decimal | None = Field(
        default=None, gt=0
    )

    loan_purpose: str | None = Field(
        default=None, min_length=2, max_length=255
    )