import re
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field, field_validator

_PLAIN_AMOUNT_PATTERN = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)")
_WESTERN_AMOUNT_PATTERN = re.compile(
    r"[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?"
)
_INDIAN_AMOUNT_PATTERN = re.compile(
    r"[+-]?\d{1,2}(?:,\d{2})+,\d{3}(?:\.\d+)?"
)


def normalize_financial_decimal(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None

        normalized = re.sub(r"^INR\s*", "", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"^₹\s*", "", normalized)
        valid_format = any(
            pattern.fullmatch(normalized)
            for pattern in (
                _PLAIN_AMOUNT_PATTERN,
                _WESTERN_AMOUNT_PATTERN,
                _INDIAN_AMOUNT_PATTERN,
            )
        )
        if not valid_format:
            raise ValueError(
                "Financial amount must be a numeric value, optionally "
                "formatted with INR or ₹ and valid digit-grouping commas."
            )
        return normalized.replace(",", "")
    return value


FinancialDecimal = Annotated[
    Decimal | None,
    BeforeValidator(normalize_financial_decimal),
]


class LoanRepayment(BaseModel):
    payment_date: str | None = None
    amount: FinancialDecimal = None
    payment_status: str | None = None


class LoanStatementExtraction(BaseModel):
    borrower_name: str | None = None
    lender_name: str | None = None
    loan_account_number_last4: str | None = None
    loan_type: str | None = None
    statement_period_start: str | None = None
    statement_period_end: str | None = None

    original_loan_amount: FinancialDecimal = None
    total_disbursed_amount: FinancialDecimal = None
    outstanding_principal: FinancialDecimal = None
    emi_amount: FinancialDecimal = None
    interest_rate: FinancialDecimal = None
    interest_rate_type: str | None = None
    original_loan_tenure_months: int | None = None
    remaining_tenure_months: int | None = None

    instalments_paid: int | None = None
    next_emi_due_date: str | None = None
    overdue_amount: FinancialDecimal = None
    days_past_due: int | None = None
    repayment_history: list[LoanRepayment] = Field(default_factory=list)
    penalties_or_additional_charges: FinancialDecimal = None
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
