import re

from app.schemas.bank_statement import (
    BankStatementExtraction,
    ClassifiedBankTransaction,
    BankTransaction,
    TransactionCategory,
)


def classify_bank_statement_transactions(
    bank_statement: BankStatementExtraction,
) -> list[ClassifiedBankTransaction]:
    return [
        _classify_transaction(transaction)
        for transaction in bank_statement.transactions
    ]


def _classify_transaction(
    transaction: BankTransaction,
) -> ClassifiedBankTransaction:
    description = (transaction.description or "").casefold()
    has_credit = transaction.credit is not None and transaction.credit > 0
    has_debit = transaction.debit is not None and transaction.debit > 0
    if has_credit == has_debit:
        category, reason = (
            "other_uncertain",
            "Transaction direction is missing or ambiguous.",
        )
    else:
        category, reason = _classify_description(
            description,
            is_credit=has_credit,
        )

    return ClassifiedBankTransaction(
        **transaction.model_dump(),
        category=category,
        classification_reason=reason,
    )


def _classify_description(
    description: str,
    is_credit: bool,
) -> tuple[TransactionCategory, str]:
    if _contains_any(
        description,
        ("refund", "reversal", "reversed", "chargeback", "cashback"),
    ):
        return (
            "refund_or_reversal",
            "Description explicitly indicates a refund, reversal, or chargeback.",
        )

    if _contains_any(
        description,
        (
            "internal transfer",
            "own account",
            "self transfer",
            "between accounts",
            "account sweep",
            "sweep transfer",
        ),
    ):
        return (
            "internal_transfer",
            "Description explicitly indicates a transfer between the customer's accounts.",
        )

    if is_credit:
        if _contains_any(
            description,
            ("salary", "payroll", "wages", "monthly pay"),
        ):
            return (
                "salary",
                "Credit description explicitly identifies salary or payroll.",
            )
        if _contains_any(
            description,
            (
                "interest credit",
                "dividend",
                "pension credit",
                "maturity proceeds",
                "investment income",
                "rent received",
                "rental income",
            ),
        ):
            return (
                "other_income",
                "Credit description explicitly identifies a non-salary income source.",
            )
        return (
            "other_uncertain",
            "A credit is not treated as income without supporting description evidence.",
        )

    if _contains_any(
        description,
        (
            "emi",
            "loan repayment",
            "loan installment",
            "loan instalment",
            "mortgage repayment",
            "loan payment",
        ),
    ):
        return (
            "loan_emi",
            "Debit description explicitly identifies a loan repayment or EMI.",
        )
    if _contains_any(description, ("rent", "lease payment")):
        return "rent", "Debit description explicitly identifies rent or lease payment."
    if _contains_any(
        description,
        (
            "electricity",
            "electric bill",
            "water bill",
            "gas bill",
            "utility bill",
            "broadband",
            "internet bill",
            "mobile bill",
            "telephone bill",
            "telecom bill",
        ),
    ):
        return "utilities", "Debit description identifies a utility or telecom bill."
    if _contains_any(
        description,
        ("grocery", "groceries", "supermarket", "super market", "food mart"),
    ):
        return "groceries", "Debit description identifies a grocery purchase."
    if _contains_any(
        description,
        (
            "shopping",
            "retail purchase",
            "e-commerce",
            "ecommerce",
            "apparel",
            "clothing",
            "fashion",
        ),
    ):
        return "shopping", "Debit description identifies a retail or shopping purchase."
    if _contains_any(
        description,
        (
            "hospital",
            "clinic",
            "pharmacy",
            "medical",
            "healthcare",
            "health care",
            "doctor",
            "diagnostic",
        ),
    ):
        return "healthcare", "Debit description identifies a healthcare service or purchase."
    if _contains_any(
        description,
        ("insurance premium", "insurance policy", "life insurance", "health insurance"),
    ):
        return "insurance", "Debit description explicitly identifies an insurance payment."
    if _contains_any(
        description,
        ("cash withdrawal", "atm withdrawal", "atm cash"),
    ):
        return "cash_withdrawal", "Debit description explicitly identifies a cash withdrawal."

    return (
        "other_uncertain",
        "Debit description does not provide enough evidence for a specific category.",
    )


def _contains_any(description: str, keywords: tuple[str, ...]) -> bool:
    return any(
        re.search(
            rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])",
            description,
        )
        is not None
        for keyword in keywords
    )
