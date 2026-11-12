from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, localcontext
from typing import get_args
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.application import LoanApplication
from app.models.document import Document
from app.models.extraction import DocumentExtraction
from app.models.financial_analysis import FinancialAnalysis
from app.schemas.bank_statement import BankStatementExtraction, TransactionCategory
from app.schemas.financial import PayslipExtraction
from app.schemas.financial_analysis import FinancialCalculationRequest
from app.schemas.loan_statement import LoanStatementExtraction
from app.services.financial_analysis import save_financial_analysis
from app.services.financial_verification import compare_financial_data

_ZERO = Decimal("0")
_ONE = Decimal("1")
_ROUNDING_TOLERANCE = Decimal("0.01")
_CALCULATION_VERSION = "1.0"
_NON_RECURRING_INCOME_TERMS = (
    "consult",
    "reimburse",
    "refund",
    "reversal",
    "interest",
    "dividend",
    "cashback",
)


class FinancialCalculationDataUnavailable(Exception):
    def __init__(self, missing_data: list[str]) -> None:
        self.missing_data = missing_data
        super().__init__(
            "Required saved financial extraction data unavailable: "
            f"{', '.join(missing_data)}."
        )


def calculate_and_save_financial_analysis(
    db: Session,
    application: LoanApplication,
    request: FinancialCalculationRequest,
) -> FinancialAnalysis:
    data = _load_saved_data(db, application.id)
    missing = [
        label
        for label, value in (
            ("payslip extraction", data["payslips"]),
            ("bank statement extraction", data["bank_statements"]),
            ("bank transaction classification", data["classifications"]),
        )
        if not value
    ]
    if missing:
        raise FinancialCalculationDataUnavailable(missing)
    if not _has_complete_classification(data["bank_statements"], data["classifications"]):
        raise FinancialCalculationDataUnavailable(
            ["complete saved bank transaction classification"]
        )

    calculation_results = _calculate(
        application=application,
        payslips=data["payslips"],
        bank_statements=data["bank_statements"],
        classifications=data["classifications"],
        loan_statements=data["loan_statements"],
        request=request,
    )
    inputs = {
        "max_foir_percent": request.max_foir_percent,
        "proposed_annual_interest_rate": request.proposed_annual_interest_rate,
        "proposed_tenure_months": request.proposed_tenure_months,
        "minimum_monthly_reserve": request.minimum_monthly_reserve,
        "requested_loan_amount": application.requested_loan_amount,
    }

    return save_financial_analysis(
        db=db,
        application_id=application.id,
        source_document_ids=sorted(data["source_document_ids"]),
        calculation_inputs=inputs,
        calculation_results=calculation_results,
        calculation_version=_CALCULATION_VERSION,
    )


def _load_saved_data(db: Session, application_id: int) -> dict[str, Any]:
    rows = db.execute(
        select(Document, DocumentExtraction)
        .join(
            DocumentExtraction,
            DocumentExtraction.document_id == Document.id,
        )
        .where(
            Document.application_id == application_id,
            DocumentExtraction.extraction_type.in_(
                (
                    "payslip",
                    "bank_statement",
                    "bank_transaction_classification",
                    "loan_statement",
                )
            ),
        )
        .order_by(Document.created_at, Document.id)
    ).all()

    result: dict[str, Any] = {
        "payslips": [],
        "bank_statements": [],
        "classifications": {},
        "loan_statements": [],
        "source_document_ids": set(),
    }
    for document, extraction in rows:
        extraction_type = extraction.extraction_type
        if extraction_type == "payslip" and document.document_type == "payslip":
            result["payslips"].append(
                (document.id, PayslipExtraction.model_validate(extraction.extracted_data))
            )
        elif (
            extraction_type == "bank_statement"
            and document.document_type == "bank_statement"
        ):
            result["bank_statements"].append(
                (
                    document.id,
                    BankStatementExtraction.model_validate(
                        extraction.extracted_data
                    ),
                )
            )
            result["classifications"].setdefault(document.id, None)
        elif extraction_type == "bank_transaction_classification":
            result["classifications"][document.id] = extraction.extracted_data
        elif (
            extraction_type == "loan_statement"
            and document.document_type == "existing_loan_statement"
        ):
            result["loan_statements"].append(
                (
                    document.id,
                    LoanStatementExtraction.model_validate(
                        extraction.extracted_data
                    ),
                )
            )
        result["source_document_ids"].add(document.id)

    return result


def _calculate(
    application: LoanApplication,
    payslips: list[tuple[int, PayslipExtraction]],
    bank_statements: list[tuple[int, BankStatementExtraction]],
    classifications: dict[int, dict | None],
    loan_statements: list[tuple[int, LoanStatementExtraction]],
    request: FinancialCalculationRequest,
) -> dict[str, Any]:
    warnings: list[str] = []
    missing_inputs: list[str] = []
    findings: list[dict[str, Any]] = []
    evidence: list[str] = []
    latest_payslip_id, payslip = payslips[-1]
    latest_bank_id, latest_bank = bank_statements[-1]
    statement_periods = _statement_periods(bank_statements)
    month_count = len(
        {
            month
            for _, statement in bank_statements
            for month in _covered_months(statement)
        }
    )
    coverage_months = Decimal(month_count) if month_count else None
    if coverage_months is None:
        warnings.append(
            "Bank statement period dates are incomplete; monthly expense "
            "averages cannot be calculated."
        )
        missing_inputs.append("complete bank statement period dates")

    tx_rows, classified_rows = _collect_transactions(
        bank_statements,
        classifications,
    )
    for document_id, statement in bank_statements:
        evidence.extend(
            f"Bank statement {document_id}: {item}"
            for item in statement.evidence
        )
    evidence.extend(
        f"Payslip {latest_payslip_id}: {item}" for item in payslip.evidence
    )

    salary_months: dict[str, Decimal] = defaultdict(lambda: _ZERO)
    category_totals: dict[str, Decimal] = defaultdict(lambda: _ZERO)
    income_candidates: dict[str, list[tuple[str, Decimal]]] = defaultdict(list)
    one_time_credits = _ZERO
    reimbursements = _ZERO
    refunds = _ZERO
    cash_outflows = _ZERO
    observed_non_debt_expenses = _ZERO
    categorized_other = _ZERO
    unclassified_debits = _ZERO
    statement_emi_evidence: list[str] = []

    for transaction, category, document_id in classified_rows:
        debit = transaction.debit if transaction.debit and transaction.debit > _ZERO else _ZERO
        credit = transaction.credit if transaction.credit and transaction.credit > _ZERO else _ZERO
        description = transaction.description or "Description unavailable"
        month = _month_key(transaction.transaction_date)

        if credit:
            if category == "salary":
                if month:
                    salary_months[month] += credit
            elif category == "reimbursement":
                reimbursements += credit
                one_time_credits += credit
            elif category == "refund_or_reversal":
                refunds += credit
                one_time_credits += credit
            elif category == "other_income":
                if any(term in description.casefold() for term in _NON_RECURRING_INCOME_TERMS):
                    one_time_credits += credit
                elif month:
                    income_candidates[description.casefold()].append((month, credit))
                else:
                    one_time_credits += credit
            else:
                one_time_credits += credit

        if not debit or category == "internal_transfer":
            continue
        if category == "loan_emi":
            continue
        cash_outflows += debit
        observed_non_debt_expenses += debit
        if category in {
            "rent",
            "groceries",
            "utilities",
            "healthcare",
            "insurance",
            "shopping",
        }:
            category_totals[category] += debit
        elif category == "other_uncertain":
            unclassified_debits += debit
        else:
            categorized_other += debit

    for transaction, category, _ in classified_rows:
        if transaction.debit and transaction.debit > _ZERO and category == "loan_emi":
            cash_outflows += transaction.debit

    if payslip.net_salary is None:
        salary_status = "needs_review"
        verified_salary = None
        missing_inputs.append("payslip net salary")
        salary_explanation = "Payslip net salary is unavailable."
    else:
        matching_months = [
            month
            for month, amount in salary_months.items()
            if abs(amount - payslip.net_salary) <= _ROUNDING_TOLERANCE
        ]
        if matching_months:
            salary_status = "matched"
            verified_salary = payslip.net_salary
            salary_explanation = (
                "Payslip net salary matches a bank salary credit total in "
                f"statement month(s): {', '.join(sorted(matching_months))}."
            )
        elif salary_months:
            salary_status = "mismatch"
            verified_salary = None
            salary_explanation = (
                "Payslip net salary does not match the identified bank salary "
                "credit total for any available month."
            )
            warnings.append(salary_explanation)
        else:
            salary_status = "needs_review"
            verified_salary = None
            salary_explanation = (
                "No dated salary credit is available to verify the payslip "
                "net salary."
            )
            warnings.append(salary_explanation)
    findings.append(
        {
            "check_name": "payslip_vs_bank_salary",
            "status": salary_status,
            "expected_value": payslip.net_salary,
            "actual_value": dict(salary_months),
            "explanation": salary_explanation,
            "supporting_evidence": [
                f"Payslip {latest_payslip_id}: net salary {payslip.net_salary}",
                *[
                    f"{month}: bank salary credits {amount}"
                    for month, amount in sorted(salary_months.items())
                ],
            ],
        }
    )
    if salary_status != "matched":
        missing_inputs.append("verified payslip salary")

    recurring_income_values: list[Decimal] = []
    for description, payments in income_candidates.items():
        by_month: dict[str, Decimal] = defaultdict(lambda: _ZERO)
        for month, amount in payments:
            by_month[month] += amount
        if len(by_month) >= 3 and len(set(by_month.values())) == 1:
            recurring_income_values.append(next(iter(by_month.values())))
        else:
            one_time_credits += sum(by_month.values(), _ZERO)
    other_recurring_income = (
        sum(recurring_income_values, _ZERO)
        if recurring_income_values
        else _ZERO
    )
    if income_candidates and not recurring_income_values:
        warnings.append(
            "Non-salary credits did not meet the three-month consistent "
            "description-and-amount rule for recurring income."
        )
    eligible_income = (
        verified_salary + other_recurring_income
        if verified_salary is not None
        else None
    )
    gross_income = payslip.gross_salary
    if gross_income is None:
        missing_inputs.append("payslip gross salary")

    loan_totals = _loan_obligations(loan_statements)
    loan_emi_total = loan_totals["monthly_emi"]
    outstanding_principal = loan_totals["outstanding_principal"]
    number_loans = loan_totals["number_of_loans"]
    other_debt = _ZERO
    potential_debts: list[dict[str, Any]] = []
    statement_emi_values = loan_totals["emi_values"]
    seen_unmatched_emi: set[tuple[str, Decimal]] = set()
    for transaction, category, document_id in classified_rows:
        if category != "loan_emi" or not transaction.debit or transaction.debit <= _ZERO:
            continue
        matched_statement = any(
            abs(transaction.debit - emi) <= _ROUNDING_TOLERANCE
            for emi in statement_emi_values
        )
        if matched_statement:
            statement_emi_evidence.append(
                f"Bank statement {document_id}: payment {transaction.debit} "
                "supports an EMI reported in an existing loan statement."
            )
            continue
        description_key = (transaction.description or "unknown").casefold()
        key = (description_key, transaction.debit)
        if key in seen_unmatched_emi:
            continue
        seen_unmatched_emi.add(key)
        other_debt += transaction.debit
        potential_debts.append(
            {
                "description": transaction.description,
                "monthly_amount": transaction.debit,
                "status": "potential_needs_review",
                "source_document_id": document_id,
            }
        )
        warnings.append(
            "A bank transaction is classified as loan EMI but has no "
            "matching loan statement; it is included as a potential debt "
            "obligation pending review."
        )

    total_debt_obligations = loan_emi_total + other_debt
    observed_expenses = {
        "rent": category_totals["rent"],
        "groceries": category_totals["groceries"],
        "utilities": category_totals["utilities"],
        "healthcare": category_totals["healthcare"],
        "insurance": category_totals["insurance"],
        "shopping": category_totals["shopping"],
        "other_expenses": categorized_other,
        "unclassified_debits": unclassified_debits,
        "total_observed_expenses": observed_non_debt_expenses,
        "total_observed_cash_outflows": cash_outflows,
    }
    monthly_average_expenses = (
        {
            key: value / coverage_months
            for key, value in observed_expenses.items()
        }
        if coverage_months
        else None
    )
    living_expenses = (
        observed_non_debt_expenses / coverage_months
        if coverage_months
        else None
    )
    disposable_income = (
        eligible_income - total_debt_obligations - living_expenses
        if eligible_income is not None and living_expenses is not None
        else None
    )
    cash_flow_surplus = disposable_income
    foir = (
        total_debt_obligations / eligible_income * Decimal("100")
        if eligible_income is not None and eligible_income > _ZERO
        else None
    )
    dti = (
        total_debt_obligations / gross_income * Decimal("100")
        if gross_income is not None and gross_income > _ZERO
        else None
    )
    if eligible_income is None:
        missing_inputs.append("eligible monthly income for FOIR")
    if living_expenses is None:
        missing_inputs.append("statement coverage period for monthly expenses")

    max_obligations = (
        eligible_income * request.max_foir_percent / Decimal("100")
        if eligible_income is not None and request.max_foir_percent is not None
        else None
    )
    foir_headroom = (
        max_obligations - total_debt_obligations
        if max_obligations is not None
        else None
    )
    if request.max_foir_percent is None:
        missing_inputs.append("max_foir_percent lender policy")
    cash_flow_capacity = (
        disposable_income - request.minimum_monthly_reserve
        if disposable_income is not None
        and request.minimum_monthly_reserve is not None
        else None
    )
    if request.minimum_monthly_reserve is None:
        missing_inputs.append("minimum_monthly_reserve lender policy")
    affordable_emi = (
        max(_ZERO, min(foir_headroom, cash_flow_capacity))
        if foir_headroom is not None and cash_flow_capacity is not None
        else None
    )
    maximum_loan_amount = (
        _principal_for_emi(
            affordable_emi,
            request.proposed_annual_interest_rate,
            request.proposed_tenure_months,
        )
        if affordable_emi is not None
        and request.proposed_annual_interest_rate is not None
        and request.proposed_tenure_months is not None
        else None
    )
    if request.proposed_annual_interest_rate is None:
        missing_inputs.append("proposed_annual_interest_rate")
    if request.proposed_tenure_months is None:
        missing_inputs.append("proposed_tenure_months")

    proposed_emi = None
    projected_foir = None
    remaining_after_proposed = None
    proposed_fits = None
    if (
        request.proposed_annual_interest_rate is not None
        and request.proposed_tenure_months is not None
        and application.requested_loan_amount is not None
    ):
        proposed_emi = _emi_for_principal(
            application.requested_loan_amount,
            request.proposed_annual_interest_rate,
            request.proposed_tenure_months,
        )
        if eligible_income is not None and eligible_income > _ZERO:
            projected_foir = (
                (total_debt_obligations + proposed_emi)
                / eligible_income
                * Decimal("100")
            )
        if disposable_income is not None:
            remaining_after_proposed = disposable_income - proposed_emi
        if affordable_emi is not None:
            proposed_fits = proposed_emi <= affordable_emi

    verification = compare_financial_data(
        application_id=application.id,
        payslip_document_id=latest_payslip_id,
        bank_statement_document_id=latest_bank_id,
        payslip=payslip,
        bank_statement=latest_bank,
    )
    findings.extend(
        finding.model_dump(mode="python")
        for finding in verification.findings
    )
    if any(finding.status in {"mismatch", "needs_review"} for finding in verification.findings):
        warnings.append(
            "Existing cross-document verification contains mismatches or "
            "items requiring manual review."
        )

    expense_period_label = (
        f"Observed across {coverage_months} covered calendar month(s)"
        if coverage_months
        else "Observed statement period; coverage unavailable"
    )
    assumptions = [
        "Payslip net salary is counted once only when a dated classified bank salary-credit month matches it within 0.01.",
        "Other income is eligible only when the same description and amount recur across at least three distinct statement months.",
        "Consulting, reimbursements, refunds, interest, dividends, and unverified credits are excluded from recurring income.",
        "Internal transfers are excluded from income, expenses, and cash outflows.",
        "Classified loan EMI debits are excluded from living expenses and counted only as loan statement EMI or a potential unmatched obligation.",
        "Monthly expense averages use the number of unique calendar months explicitly covered by statement periods; otherwise only observed totals are reported.",
        "Cash-flow surplus equals eligible monthly income minus monthly existing debt obligations and monthly observed non-debt expenses.",
        "FOIR includes existing monthly debt obligations only; no rent or living expense is included by default.",
        "A reducing-balance loan formula is used for estimated EMI and supported principal.",
    ]
    if statement_emi_evidence:
        evidence.extend(statement_emi_evidence)
    if loan_totals["evidence"]:
        evidence.extend(loan_totals["evidence"])
    if not loan_statements:
        warnings.append(
            "No saved existing loan statement extraction was found; debt "
            "obligations detected from bank EMI transactions are provisional."
        )

    return {
        "application_information": {
            "application_id": application.id,
            "applicant_name": application.applicant_name,
            "requested_loan_amount": application.requested_loan_amount,
        },
        "income_summary": {
            "gross_monthly_income": gross_income,
            "verified_monthly_salary": verified_salary,
            "other_recurring_income": other_recurring_income,
            "total_eligible_monthly_income": eligible_income,
            "one_time_credits": one_time_credits,
            "reimbursements": reimbursements,
            "salary_verification_status": salary_status,
            "salary_credit_by_month": dict(salary_months),
        },
        "expense_summary": {
            **observed_expenses,
            "monthly_average": monthly_average_expenses,
            "observation_period": expense_period_label,
        },
        "existing_liabilities": {
            "number_of_existing_loans": number_loans,
            "total_outstanding_principal": outstanding_principal,
            "total_existing_monthly_emi": loan_emi_total,
            "other_debt_obligations": other_debt,
            "total_monthly_debt_obligations": total_debt_obligations,
            "potential_unmatched_emi_obligations": potential_debts,
        },
        "financial_health": {
            "foir_percent": foir,
            "foir_formula": "(monthly debt obligations / eligible monthly income) * 100",
            "debt_to_income_ratio_percent": dti,
            "debt_to_income_formula": "(monthly debt obligations / gross monthly income) * 100",
            "disposable_income": disposable_income,
            "cash_flow_surplus": cash_flow_surplus,
            "cash_flow_period": expense_period_label,
        },
        "repayment_capacity": {
            "maximum_permitted_obligations": max_obligations,
            "additional_emi_capacity": foir_headroom,
            "affordable_new_emi": affordable_emi,
            "maximum_eligible_loan_amount": maximum_loan_amount,
            "proposed_loan_emi": proposed_emi,
            "projected_foir_percent": projected_foir,
            "remaining_monthly_income_after_proposed_emi": remaining_after_proposed,
            "proposed_emi_fits_indicative_capacity": proposed_fits,
            "assumptions": {
                "max_foir_percent": request.max_foir_percent,
                "minimum_monthly_reserve": request.minimum_monthly_reserve,
                "proposed_annual_interest_rate": request.proposed_annual_interest_rate,
                "proposed_tenure_months": request.proposed_tenure_months,
                "repayment_method": "monthly reducing balance",
            },
        },
        "data_quality": {
            "statement_periods_used": statement_periods,
            "number_of_months_available": month_count or None,
            "missing_inputs": sorted(set(missing_inputs)),
            "warnings": list(dict.fromkeys(warnings)),
            "supporting_evidence": list(dict.fromkeys(evidence)),
            "calculation_assumptions": assumptions,
            "findings": findings,
            "overall_status": (
                "needs_review"
                if warnings
                or any(
                    item.get("status") in {"mismatch", "needs_review"}
                    for item in findings
                )
                else "matched"
            ),
        },
    }


def _collect_transactions(
    statements: list[tuple[int, BankStatementExtraction]],
    classifications: dict[int, dict | None],
) -> tuple[list[tuple[Any, int]], list[tuple[Any, str, int]]]:
    tx_rows: list[tuple[Any, int]] = []
    classified_rows: list[tuple[Any, str, int]] = []
    seen: set[tuple[Any, ...]] = set()
    for document_id, statement in statements:
        classification_data = classifications.get(document_id)
        saved = (
            classification_data.get("transactions")
            if isinstance(classification_data, dict)
            else None
        )
        category_by_index = {
            item.get("transaction_index"): item.get("category")
            for item in saved or []
            if isinstance(item, dict)
        }
        for index, transaction in enumerate(statement.transactions):
            key = (
                transaction.transaction_date,
                transaction.description,
                transaction.debit,
                transaction.credit,
            )
            if key in seen:
                continue
            seen.add(key)
            tx_rows.append((transaction, document_id))
            category = category_by_index.get(index)
            if category:
                classified_rows.append((transaction, category, document_id))
    return tx_rows, classified_rows


def _has_complete_classification(
    bank_statements: list[tuple[int, BankStatementExtraction]],
    classifications: dict[int, dict | None],
) -> bool:
    allowed_categories = set(get_args(TransactionCategory))
    for document_id, statement in bank_statements:
        record = classifications.get(document_id)
        saved = record.get("transactions") if isinstance(record, dict) else None
        if not isinstance(saved, list) or len(saved) != len(statement.transactions):
            return False
        if not all(
            isinstance(item, dict)
            and item.get("transaction_index") == index
            and item.get("category") in allowed_categories
            and isinstance(item.get("classification_reason"), str)
            for index, item in enumerate(saved)
        ):
            return False
    return True


def _loan_obligations(
    loan_statements: list[tuple[int, LoanStatementExtraction]],
) -> dict[str, Any]:
    loans: dict[tuple[Any, ...], tuple[int, LoanStatementExtraction]] = {}
    evidence: list[str] = []
    for document_id, statement in loan_statements:
        key = (
            (statement.lender_name or "").casefold(),
            statement.loan_account_number_last4 or document_id,
        )
        loans[key] = (document_id, statement)

    emis: list[Decimal] = []
    principals: list[Decimal] = []
    for document_id, statement in loans.values():
        if statement.emi_amount is not None:
            emis.append(statement.emi_amount)
            evidence.append(
                f"Loan statement {document_id}: reported monthly EMI "
                f"{statement.emi_amount}."
            )
        if statement.outstanding_principal is not None:
            principals.append(statement.outstanding_principal)
            evidence.append(
                f"Loan statement {document_id}: outstanding principal "
                f"{statement.outstanding_principal}."
            )
    return {
        "number_of_loans": len(loans),
        "monthly_emi": sum(emis, _ZERO),
        "outstanding_principal": sum(principals, _ZERO),
        "emi_values": emis,
        "evidence": evidence,
    }


def _statement_periods(
    statements: list[tuple[int, BankStatementExtraction]],
) -> list[dict[str, Any]]:
    return [
        {
            "document_id": document_id,
            "start": statement.statement_period_start,
            "end": statement.statement_period_end,
        }
        for document_id, statement in statements
    ]


def _covered_months(statement: BankStatementExtraction) -> list[str]:
    start = _parse_date(statement.statement_period_start)
    end = _parse_date(statement.statement_period_end)
    if not start or not end or end < start:
        return []
    months = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append(f"{year:04d}-{month:02d}")
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return months


def _month_key(value: str | None) -> str | None:
    parsed = _parse_date(value)
    return parsed.strftime("%Y-%m") if parsed else None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    normalized = value.strip()
    formats = (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d %B %Y",
        "%d %b %Y",
        "%B %Y",
        "%b %Y",
    )
    for date_format in formats:
        try:
            parsed = datetime.strptime(normalized, date_format)
            if date_format in {"%B %Y", "%b %Y"}:
                return date(parsed.year, parsed.month, 1)
            return parsed.date()
        except ValueError:
            continue
    return None


def _emi_for_principal(
    principal: Decimal,
    annual_rate_percent: Decimal,
    tenure_months: int,
) -> Decimal:
    if tenure_months <= 0:
        raise ValueError("Proposed tenure must be greater than zero")
    monthly_rate = annual_rate_percent / Decimal("1200")
    if monthly_rate == _ZERO:
        return principal / Decimal(tenure_months)
    with localcontext() as context:
        context.prec = 40
        factor = (_ONE + monthly_rate) ** tenure_months
        return principal * monthly_rate * factor / (factor - _ONE)


def _principal_for_emi(
    emi: Decimal,
    annual_rate_percent: Decimal,
    tenure_months: int,
) -> Decimal:
    if tenure_months <= 0:
        raise ValueError("Proposed tenure must be greater than zero")
    monthly_rate = annual_rate_percent / Decimal("1200")
    if monthly_rate == _ZERO:
        return emi * Decimal(tenure_months)
    with localcontext() as context:
        context.prec = 40
        factor = (_ONE + monthly_rate) ** tenure_months
        return emi * (factor - _ONE) / (monthly_rate * factor)
