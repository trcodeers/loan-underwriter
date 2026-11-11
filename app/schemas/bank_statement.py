import re
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class BankTransaction(BaseModel):
    transaction_date: str | None = None
    description: str | None = None
    debit: Decimal | None = None
    credit: Decimal | None = None
    balance: Decimal | None = None


class BankStatementExtraction(BaseModel):
    statement_total_credits: Decimal | None = Field(
        default=None,
        description="Total credits explicitly reported in the statement summary",
    )
    statement_total_debits: Decimal | None = Field(
        default=None,
        description="Total debits explicitly reported in the statement summary",
    )
    account_holder_name: str | None = None
    bank_name: str | None = None
    account_number_last4: str | None = None
    statement_period_start: str | None = None
    statement_period_end: str | None = None
    opening_balance: Decimal | None = None
    closing_balance: Decimal | None = None
    currency: str | None = None
    transactions: list[BankTransaction] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)

    @field_validator("account_number_last4", mode="before")
    @classmethod
    def retain_only_account_last4(cls, value: object) -> str | None:
        if value is None:
            return None

        digits = re.sub(r"\D", "", str(value))
        return digits[-4:] if len(digits) >= 4 else None

    @field_validator("evidence")
    @classmethod
    def redact_long_number_sequences(cls, evidence: list[str]) -> list[str]:
        return [
            re.sub(r"(?<!\d)\d{8,}(?!\d)", "[REDACTED]", item)
            for item in evidence
        ]


class BankStatementExtractionResponse(BankStatementExtraction):
    document_id: int
    application_id: int
    original_filename: str
