from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


VerificationStatus = Literal["matched", "mismatch", "needs_review"]
VerificationValue = Decimal | str | list[str] | None


class FinancialVerificationFinding(BaseModel):
    check_name: str
    status: VerificationStatus
    expected_value: VerificationValue = None
    actual_value: VerificationValue = None
    difference: Decimal | None = None
    explanation: str
    supporting_evidence: list[str] = Field(default_factory=list)


class FinancialVerificationResponse(BaseModel):
    application_id: int
    payslip_document_id: int
    bank_statement_document_id: int
    overall_status: VerificationStatus
    findings: list[FinancialVerificationFinding]
    summary: str
