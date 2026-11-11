import re
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class LoanRepayment(BaseModel):
    payment_date: str | None = None
    amount: Decimal | None = None
    payment_status: str | None = None


class LoanStatementExtraction(BaseModel):
    borrower_name: str | None = None
    lender_name: str | None = None
    loan_account_number_last4: str | None = None
    loan_type: str | None = None
    statement_period_start: str | None = None
    statement_period_end: str | None = None

    original_loan_amount: Decimal | None = None
    total_disbursed_amount: Decimal | None = None
    outstanding_principal: Decimal | None = None
    emi_amount: Decimal | None = None
    interest_rate: Decimal | None = None
    interest_rate_type: str | None = None
    original_loan_tenure_months: int | None = None
    remaining_tenure_months: int | None = None

    instalments_paid: int | None = None
    next_emi_due_date: str | None = None
    overdue_amount: Decimal | None = None
    days_past_due: int | None = None
    repayment_history: list[LoanRepayment] = Field(default_factory=list)
    penalties_or_additional_charges: Decimal | None = None
    currency: str | None = None

    missing_fields: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(
        default_factory=list,
        description="Short exact excerpts supporting extracted values.",
    )

    @field_validator("loan_account_number_last4", mode="before")
    @classmethod
    def retain_only_account_last4(cls, value: object) -> str | None:
        if value is None:
            return None
        digits = re.sub(r"\D", "", str(value))
        return digits[-4:] if digits else None

    @field_validator("evidence")
    @classmethod
    def redact_long_number_sequences(cls, evidence: list[str]) -> list[str]:
        return [
            re.sub(r"(?<!\d)\d{8,}(?!\d)", "[REDACTED]", item)
            for item in evidence
        ]


class LoanStatementExtractionResponse(LoanStatementExtraction):
    document_id: int
    application_id: int
    original_filename: str
