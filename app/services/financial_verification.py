import re
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.extraction import DocumentExtraction
from app.schemas.bank_statement import (
    BankStatementExtraction,
    BankTransaction,
)
from app.schemas.financial import PayslipExtraction
from app.schemas.verification import (
    FinancialVerificationFinding,
    FinancialVerificationResponse,
    VerificationStatus,
)

_ZERO = Decimal("0")
_CURRENCY_ROUNDING_TOLERANCE = Decimal("0.01")
_SALARY_TERMS = ("salary", "payroll", "wages", "monthly pay")
_GENERIC_EMPLOYER_TOKENS = {
    "and",
    "co",
    "company",
    "corp",
    "corporation",
    "inc",
    "india",
    "limited",
    "llc",
    "llp",
    "ltd",
    "pvt",
    "private",
    "the",
}


class FinancialVerificationDataUnavailable(Exception):
    def __init__(self, missing_document_types: list[str]) -> None:
        self.missing_document_types = missing_document_types
        super().__init__(
            "Required saved extraction(s) unavailable: "
            f"{', '.join(missing_document_types)}."
        )


def verify_application_finances(
    db: Session,
    application_id: int,
) -> FinancialVerificationResponse:
    statement = (
        select(DocumentExtraction, Document)
        .join(Document, Document.id == DocumentExtraction.document_id)
        .where(
            Document.application_id == application_id,
            Document.document_type.in_(("payslip", "bank_statement")),
            DocumentExtraction.extraction_type.in_(
                ("payslip", "bank_statement")
            ),
        )
        .order_by(
            Document.created_at.desc(),
            Document.id.desc(),
            DocumentExtraction.id.desc(),
        )
    )
    extraction_rows = db.execute(statement).all()

    latest: dict[str, tuple[DocumentExtraction, Document]] = {}
    for extraction, document in extraction_rows:
        if extraction.extraction_type == document.document_type:
            latest.setdefault(extraction.extraction_type, (extraction, document))

    missing_types = [
        extraction_type
        for extraction_type in ("payslip", "bank_statement")
        if extraction_type not in latest
    ]
    if missing_types:
        raise FinancialVerificationDataUnavailable(missing_types)

    payslip_extraction, payslip_document = latest["payslip"]
    bank_extraction, bank_document = latest["bank_statement"]

    payslip = PayslipExtraction.model_validate(
        payslip_extraction.extracted_data
    )
    bank_statement = BankStatementExtraction.model_validate(
        bank_extraction.extracted_data
    )

    return compare_financial_data(
        application_id=application_id,
        payslip_document_id=payslip_document.id,
        bank_statement_document_id=bank_document.id,
        payslip=payslip,
        bank_statement=bank_statement,
    )


def compare_financial_data(
    application_id: int,
    payslip_document_id: int,
    bank_statement_document_id: int,
    payslip: PayslipExtraction,
    bank_statement: BankStatementExtraction,
) -> FinancialVerificationResponse:
    findings: list[FinancialVerificationFinding] = []
    salary_candidates, amount_only_candidates = _salary_candidates(
        bank_statement.transactions,
        payslip.employer_name,
        payslip.net_salary,
    )

    findings.append(
        _compare_salary(
            payslip.net_salary,
            salary_candidates,
            amount_only_candidates,
            payslip.evidence,
        )
    )
    findings.append(
        _compare_names(
            payslip.employee_name,
            bank_statement.account_holder_name,
            payslip.evidence,
            bank_statement.evidence,
        )
    )
    findings.append(
        _compare_employer(
            payslip.employer_name,
            salary_candidates,
            payslip.evidence,
        )
    )
    findings.extend(_verify_bank_balances(bank_statement))

    statuses = {finding.status for finding in findings}
    overall_status: VerificationStatus
    if "mismatch" in statuses:
        overall_status = "mismatch"
    elif "needs_review" in statuses:
        overall_status = "needs_review"
    else:
        overall_status = "matched"

    matched_count = sum(f.status == "matched" for f in findings)
    mismatch_count = sum(f.status == "mismatch" for f in findings)
    review_count = sum(f.status == "needs_review" for f in findings)
    summary = (
        f"{matched_count} checks matched, {mismatch_count} mismatched, "
        f"and {review_count} need review. These findings do not make a "
        "loan approval or rejection decision."
    )

    return FinancialVerificationResponse(
        application_id=application_id,
        payslip_document_id=payslip_document_id,
        bank_statement_document_id=bank_statement_document_id,
        overall_status=overall_status,
        findings=findings,
        summary=summary,
    )


def _salary_candidates(
    transactions: list[BankTransaction],
    employer_name: str | None,
    net_salary: Decimal | None,
) -> tuple[list[tuple[int, BankTransaction]], list[tuple[int, BankTransaction]]]:
    candidates: list[tuple[int, BankTransaction]] = []
    amount_only_candidates: list[tuple[int, BankTransaction]] = []

    for index, transaction in enumerate(transactions, start=1):
        if transaction.credit is None or transaction.credit <= _ZERO:
            continue

        description = (transaction.description or "").casefold()
        has_salary_term = any(term in description for term in _SALARY_TERMS)
        has_employer_name = _employer_matches(
            employer_name,
            transaction.description,
        )
        if has_salary_term or has_employer_name:
            candidates.append((index, transaction))
        elif net_salary is not None and transaction.credit == net_salary:
            amount_only_candidates.append((index, transaction))

    return candidates, amount_only_candidates


def _compare_salary(
    net_salary: Decimal | None,
    candidates: list[tuple[int, BankTransaction]],
    amount_only_candidates: list[tuple[int, BankTransaction]],
    payslip_evidence: list[str],
) -> FinancialVerificationFinding:
    if len(candidates) > 1:
        return FinancialVerificationFinding(
            check_name="salary_credit",
            status="needs_review",
            expected_value=net_salary,
            actual_value=[
                _transaction_label(index, transaction)
                for index, transaction in candidates
            ],
            explanation=(
                "Multiple transactions have salary or employer indicators; "
                "the service does not select one as the salary credit."
            ),
            supporting_evidence=[
                *_relevant_evidence(payslip_evidence),
                *[
                    _transaction_label(index, transaction)
                    for index, transaction in candidates
                ],
            ],
        )

    if not candidates:
        evidence = [
            *_relevant_evidence(payslip_evidence),
            *[
                _transaction_label(index, transaction)
                for index, transaction in amount_only_candidates
            ],
        ]
        if amount_only_candidates:
            explanation = (
                "A credit matches the payslip amount, but its description "
                "does not indicate salary or the employer. Amount alone is "
                "not sufficient to identify a salary transaction."
            )
            actual_value: Decimal | str | list[str] | None = [
                _transaction_label(index, transaction)
                for index, transaction in amount_only_candidates
            ]
        else:
            explanation = (
                "No salary-like credit could be identified from transaction "
                "descriptions and employer-name evidence."
            )
            actual_value = None
        return FinancialVerificationFinding(
            check_name="salary_credit",
            status="needs_review",
            expected_value=net_salary,
            actual_value=actual_value,
            explanation=explanation,
            supporting_evidence=evidence,
        )

    index, transaction = candidates[0]
    if net_salary is None:
        return FinancialVerificationFinding(
            check_name="salary_credit",
            status="needs_review",
            actual_value=transaction.credit,
            explanation="The payslip net salary is unavailable.",
            supporting_evidence=[
                _transaction_label(index, transaction),
                *_relevant_evidence(payslip_evidence),
            ],
        )

    difference = transaction.credit - net_salary
    matched = difference == _ZERO
    return FinancialVerificationFinding(
        check_name="salary_credit",
        status="matched" if matched else "mismatch",
        expected_value=net_salary,
        actual_value=transaction.credit,
        difference=difference,
        explanation=(
            "The identified salary credit equals the payslip net salary."
            if matched
            else "The identified salary credit differs from the payslip net salary."
        ),
        supporting_evidence=[
            _transaction_label(index, transaction),
            *_relevant_evidence(payslip_evidence),
        ],
    )


def _compare_names(
    employee_name: str | None,
    account_holder_name: str | None,
    payslip_evidence: list[str],
    bank_evidence: list[str],
) -> FinancialVerificationFinding:
    if not employee_name or not account_holder_name:
        return FinancialVerificationFinding(
            check_name="employee_name_vs_account_holder",
            status="needs_review",
            expected_value=employee_name,
            actual_value=account_holder_name,
            explanation=(
                "Employee name or bank account holder name is unavailable."
            ),
            supporting_evidence=[
                *_relevant_evidence(payslip_evidence),
                *_relevant_evidence(bank_evidence),
            ],
        )

    matched = _normalize_name(employee_name) == _normalize_name(
        account_holder_name
    )
    return FinancialVerificationFinding(
        check_name="employee_name_vs_account_holder",
        status="matched" if matched else "mismatch",
        expected_value=employee_name,
        actual_value=account_holder_name,
        explanation=(
            "Employee and bank account holder names match after "
            "case-and-punctuation normalization."
            if matched
            else "Employee and bank account holder names do not match."
        ),
        supporting_evidence=[
            *_relevant_evidence(payslip_evidence),
            *_relevant_evidence(bank_evidence),
        ],
    )


def _compare_employer(
    employer_name: str | None,
    candidates: list[tuple[int, BankTransaction]],
    payslip_evidence: list[str],
) -> FinancialVerificationFinding:
    descriptions = [
        (index, transaction)
        for index, transaction in candidates
        if transaction.description
    ]

    if not employer_name or not descriptions:
        return FinancialVerificationFinding(
            check_name="employer_vs_salary_description",
            status="needs_review",
            expected_value=employer_name,
            explanation=(
                "Employer name or a salary transaction description is "
                "unavailable for comparison."
            ),
            supporting_evidence=_relevant_evidence(payslip_evidence),
        )

    matching = [
        (index, transaction)
        for index, transaction in descriptions
        if _employer_matches(employer_name, transaction.description)
    ]
    if matching:
        status: VerificationStatus = "matched"
        explanation = (
            "The employer name is represented in at least one potential "
            "salary transaction description."
        )
    else:
        status = "needs_review"
        explanation = (
            "Potential salary transactions were found, but their "
            "descriptions do not confirm the payslip employer name."
        )

    return FinancialVerificationFinding(
        check_name="employer_vs_salary_description",
        status=status,
        expected_value=employer_name,
        actual_value=[
            transaction.description or ""
            for _, transaction in descriptions
        ],
        explanation=explanation,
        supporting_evidence=[
            *_relevant_evidence(payslip_evidence),
            *[
                _transaction_label(index, transaction)
                for index, transaction in descriptions
            ],
        ],
    )


def _verify_bank_balances(
    bank_statement: BankStatementExtraction,
) -> list[FinancialVerificationFinding]:
    transactions = bank_statement.transactions
    incomplete_rows = [
        index
        for index, transaction in enumerate(transactions, start=1)
        if transaction.credit is None and transaction.debit is None
    ]
    transaction_evidence = [
        _transaction_label(index, transaction)
        for index, transaction in enumerate(transactions, start=1)
    ]
    if not transactions:
        total_status: VerificationStatus = "needs_review"
        credits: Decimal | None = None
        debits: Decimal | None = None
        total_explanation = "No transaction rows are available to total."
    elif incomplete_rows:
        total_status = "needs_review"
        credits = None
        debits = None
        total_explanation = (
            "Transaction amounts are missing for row(s) "
            f"{', '.join(map(str, incomplete_rows))}; complete totals "
            "cannot be calculated."
        )
    else:
        total_status = "matched"
        credits = sum(
            (transaction.credit or _ZERO for transaction in transactions),
            _ZERO,
        )
        debits = sum(
            (transaction.debit or _ZERO for transaction in transactions),
            _ZERO,
        )
        total_explanation = (
            "Calculated from the extracted transaction rows; a missing "
            "opposite-side amount is treated as zero for a one-sided row."
        )

    total_findings = [
        _compare_statement_total(
            check_name="total_credits",
            label="credits",
            statement_total=bank_statement.statement_total_credits,
            calculated_total=credits,
            total_status=total_status,
            total_explanation=total_explanation,
            statement_evidence=bank_statement.evidence,
            transaction_evidence=transaction_evidence,
        ),
        _compare_statement_total(
            check_name="total_debits",
            label="debits",
            statement_total=bank_statement.statement_total_debits,
            calculated_total=debits,
            total_status=total_status,
            total_explanation=total_explanation,
            statement_evidence=bank_statement.evidence,
            transaction_evidence=transaction_evidence,
        ),
    ]

    if (
        bank_statement.opening_balance is None
        or bank_statement.closing_balance is None
        or credits is None
        or debits is None
    ):
        missing_inputs = [
            name
            for name, value in (
                ("opening balance", bank_statement.opening_balance),
                ("total credits", credits),
                ("total debits", debits),
                ("closing balance", bank_statement.closing_balance),
            )
            if value is None
        ]
        reconciliation = FinancialVerificationFinding(
            check_name="bank_balance_reconciliation",
            status="needs_review",
            expected_value=None,
            actual_value=bank_statement.closing_balance,
            explanation=(
                "Cannot verify opening balance + total credits - total "
                "debits = closing balance because "
                f"{', '.join(missing_inputs)} is unavailable."
            ),
            supporting_evidence=transaction_evidence,
        )
    else:
        expected_closing = (
            bank_statement.opening_balance + credits - debits
        )
        difference = expected_closing - bank_statement.closing_balance
        matched = difference == _ZERO
        reconciliation = FinancialVerificationFinding(
            check_name="bank_balance_reconciliation",
            status="matched" if matched else "mismatch",
            expected_value=expected_closing,
            actual_value=bank_statement.closing_balance,
            difference=difference,
            explanation=(
                "Opening balance + total credits - total debits equals "
                "the reported closing balance."
                if matched
                else "Opening balance + total credits - total debits does "
                "not equal the reported closing balance."
            ),
            supporting_evidence=[
                f"Opening balance: {bank_statement.opening_balance}",
                f"Total credits: {credits}",
                f"Total debits: {debits}",
                f"Reported closing balance: {bank_statement.closing_balance}",
                *transaction_evidence,
            ],
        )

    return [
        *total_findings,
        reconciliation,
        *_verify_running_balances(bank_statement),
    ]


def _compare_statement_total(
    check_name: str,
    label: str,
    statement_total: Decimal | None,
    calculated_total: Decimal | None,
    total_status: VerificationStatus,
    total_explanation: str,
    statement_evidence: list[str],
    transaction_evidence: list[str],
) -> FinancialVerificationFinding:
    if statement_total is None:
        return FinancialVerificationFinding(
            check_name=check_name,
            status="needs_review",
            actual_value=calculated_total,
            explanation=(
                f"The statement-reported total {label} is missing; "
                f"{total_explanation}"
            ),
            supporting_evidence=[
                *_relevant_evidence(statement_evidence),
                *transaction_evidence,
            ],
        )

    if calculated_total is None or total_status == "needs_review":
        return FinancialVerificationFinding(
            check_name=check_name,
            status="needs_review",
            expected_value=statement_total,
            actual_value=calculated_total,
            explanation=(
                f"The statement-reported total {label} is available, but "
                f"the transaction total cannot be verified; {total_explanation}"
            ),
            supporting_evidence=[
                *_relevant_evidence(statement_evidence),
                *transaction_evidence,
            ],
        )

    difference = calculated_total - statement_total
    matched = abs(difference) <= _CURRENCY_ROUNDING_TOLERANCE
    return FinancialVerificationFinding(
        check_name=check_name,
        status="matched" if matched else "mismatch",
        expected_value=statement_total,
        actual_value=calculated_total,
        difference=difference,
        explanation=(
            f"Calculated transaction {label} match the statement-reported "
            f"total within the {_CURRENCY_ROUNDING_TOLERANCE} currency-unit "
            "rounding tolerance."
            if matched
            else f"Calculated transaction {label} differ from the "
            "statement-reported total."
        ),
        supporting_evidence=[
            *_relevant_evidence(statement_evidence),
            *transaction_evidence,
        ],
    )


def _verify_running_balances(
    bank_statement: BankStatementExtraction,
) -> list[FinancialVerificationFinding]:
    transactions = bank_statement.transactions
    if not transactions:
        return [
            FinancialVerificationFinding(
                check_name="running_balance",
                status="needs_review",
                explanation=(
                    "No transaction rows are available to verify running "
                    "balances."
                ),
            )
        ]

    previous_balance = bank_statement.opening_balance
    findings: list[FinancialVerificationFinding] = []

    for index, transaction in enumerate(transactions, start=1):
        evidence = [_transaction_label(index, transaction)]
        has_amount = (
            transaction.credit is not None or transaction.debit is not None
        )
        can_calculate = previous_balance is not None and has_amount
        expected_balance = (
            previous_balance
            + (transaction.credit or _ZERO)
            - (transaction.debit or _ZERO)
            if can_calculate
            else None
        )
        if (
            not can_calculate
            or transaction.balance is None
        ):
            missing = []
            if not can_calculate:
                if previous_balance is None:
                    missing.append("prior balance")
                if not has_amount:
                    missing.append("transaction amount")
            if transaction.balance is None:
                missing.append("transaction balance")
            findings.append(
                FinancialVerificationFinding(
                    check_name=f"running_balance_transaction_{index}",
                    status="needs_review",
                    expected_value=expected_balance,
                    actual_value=transaction.balance,
                    explanation=(
                        "Cannot fully verify running balance because "
                        f"{', '.join(missing)} is unavailable."
                    ),
                    supporting_evidence=evidence,
                )
            )
            if transaction.balance is not None:
                previous_balance = transaction.balance
            elif expected_balance is not None:
                previous_balance = expected_balance
            else:
                previous_balance = None
            continue

        assert expected_balance is not None
        difference = expected_balance - transaction.balance
        matched = difference == _ZERO
        findings.append(
            FinancialVerificationFinding(
                check_name=f"running_balance_transaction_{index}",
                status="matched" if matched else "mismatch",
                expected_value=expected_balance,
                actual_value=transaction.balance,
                difference=difference,
                explanation=(
                    "The transaction running balance is consistent."
                    if matched
                    else "The transaction running balance is inconsistent."
                ),
                supporting_evidence=evidence,
            )
        )
        previous_balance = transaction.balance

    return findings


def _normalize_name(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _employer_matches(
    employer_name: str | None,
    description: str | None,
) -> bool:
    if not employer_name or not description:
        return False
    employer_tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", employer_name.casefold())
        if token not in _GENERIC_EMPLOYER_TOKENS
    }
    description_tokens = set(
        re.findall(r"[a-z0-9]+", description.casefold())
    )
    if not employer_tokens:
        return False
    shared_tokens = employer_tokens & description_tokens
    required_matches = min(2, len(employer_tokens))
    return len(shared_tokens) >= required_matches


def _transaction_label(index: int, transaction: BankTransaction) -> str:
    date = transaction.transaction_date or "date unavailable"
    description = transaction.description or "description unavailable"
    amount_parts = []
    if transaction.credit is not None:
        amount_parts.append(f"credit {transaction.credit}")
    if transaction.debit is not None:
        amount_parts.append(f"debit {transaction.debit}")
    if transaction.balance is not None:
        amount_parts.append(f"balance {transaction.balance}")
    amount_summary = ", ".join(amount_parts) or "amount unavailable"
    return f"Transaction {index} ({date}): {description}; {amount_summary}"


def _relevant_evidence(evidence: list[str]) -> list[str]:
    return [item for item in evidence if item.strip()]
