import unittest
from decimal import Decimal

from app.schemas.bank_statement import BankStatementExtraction, BankTransaction
from app.schemas.financial import PayslipExtraction
from app.services.financial_verification import compare_financial_data


class FinancialVerificationTests(unittest.TestCase):
    def test_legacy_extraction_defaults_statement_totals_to_missing(self) -> None:
        bank = BankStatementExtraction.model_validate(
            {
                "account_holder_name": "Alex Morgan",
                "transactions": [],
            }
        )

        self.assertIsNone(bank.statement_total_credits)
        self.assertIsNone(bank.statement_total_debits)

    def test_synthetic_payslip_and_bank_statement_match(self) -> None:
        result = self._verify(self._synthetic_payslip(), self._synthetic_bank())

        self.assertEqual(result.overall_status, "matched")
        self.assertEqual(
            self._finding(result, "salary_credit").actual_value,
            Decimal("120800"),
        )
        self.assertEqual(
            self._finding(result, "total_credits").actual_value,
            Decimal("136275"),
        )
        self.assertEqual(
            self._finding(result, "total_credits").expected_value,
            Decimal("136275"),
        )
        self.assertEqual(self._finding(result, "total_credits").status, "matched")
        self.assertEqual(
            self._finding(result, "total_debits").actual_value,
            Decimal("100398"),
        )
        self.assertEqual(
            self._finding(result, "total_debits").expected_value,
            Decimal("100398"),
        )
        self.assertEqual(self._finding(result, "total_debits").status, "matched")
        self.assertEqual(
            self._finding(result, "bank_balance_reconciliation").status,
            "matched",
        )
        self.assertTrue(
            all(
                finding.status == "matched"
                for finding in result.findings
                if finding.check_name.startswith("running_balance_transaction_")
            )
        )

    def test_salary_difference_is_reported(self) -> None:
        bank = self._synthetic_bank()
        bank.transactions[0].credit = Decimal("100000")
        bank.transactions[0].balance = Decimal("180000")
        bank.transactions[1].balance = Decimal("195475")
        bank.transactions[2].balance = Decimal("176975")
        bank.transactions[3].debit = Decimal("61098")
        bank.transactions[3].balance = Decimal("115877")
        bank.statement_total_credits = Decimal("115475")
        bank.statement_total_debits = Decimal("79598")

        result = self._verify(self._synthetic_payslip(), bank)
        salary_finding = self._finding(result, "salary_credit")

        self.assertEqual(salary_finding.status, "mismatch")
        self.assertEqual(salary_finding.difference, Decimal("-20800"))
        self.assertEqual(
            self._finding(result, "bank_balance_reconciliation").status,
            "matched",
        )

    def test_statement_total_mismatch_is_reported(self) -> None:
        bank = self._synthetic_bank()
        bank.statement_total_credits = Decimal("136274")

        result = self._verify(self._synthetic_payslip(), bank)
        finding = self._finding(result, "total_credits")

        self.assertEqual(finding.status, "mismatch")
        self.assertEqual(finding.expected_value, Decimal("136274"))
        self.assertEqual(finding.actual_value, Decimal("136275"))
        self.assertEqual(finding.difference, Decimal("1"))

    def test_missing_statement_total_needs_review(self) -> None:
        bank = self._synthetic_bank()
        bank.statement_total_debits = None

        result = self._verify(self._synthetic_payslip(), bank)
        finding = self._finding(result, "total_debits")

        self.assertEqual(finding.status, "needs_review")
        self.assertIsNone(finding.expected_value)
        self.assertEqual(finding.actual_value, Decimal("100398"))
        self.assertIn("statement-reported total debits is missing", finding.explanation)

    def test_currency_rounding_tolerance_is_applied(self) -> None:
        bank = self._synthetic_bank()
        bank.statement_total_credits = Decimal("136275.01")

        result = self._verify(self._synthetic_payslip(), bank)

        self.assertEqual(self._finding(result, "total_credits").status, "matched")

    def test_incorrect_running_balance_is_reported(self) -> None:
        bank = self._synthetic_bank()
        bank.transactions[0].balance = Decimal("200801")

        result = self._verify(self._synthetic_payslip(), bank)

        self.assertEqual(
            self._finding(result, "running_balance_transaction_1").status,
            "mismatch",
        )
        self.assertEqual(result.overall_status, "mismatch")

    def test_multiple_salary_candidates_need_review(self) -> None:
        bank = self._synthetic_bank()
        bank.transactions.insert(
            1,
            BankTransaction(
                transaction_date="2026-10-02",
                description="APEX TECHNOLOGIES PAYROLL",
                credit=Decimal("1000"),
                balance=Decimal("201800"),
            ),
        )

        result = self._verify(self._synthetic_payslip(), bank)

        self.assertEqual(self._finding(result, "salary_credit").status, "needs_review")

    def test_amount_match_without_salary_evidence_needs_review(self) -> None:
        bank = self._synthetic_bank()
        bank.transactions[0].description = "TRANSFER FROM SAVINGS"

        result = self._verify(self._synthetic_payslip(), bank)

        self.assertEqual(self._finding(result, "salary_credit").status, "needs_review")
        self.assertIn(
            "Amount alone is not sufficient",
            self._finding(result, "salary_credit").explanation,
        )

    @staticmethod
    def _finding(result, check_name: str):
        return next(
            finding for finding in result.findings
            if finding.check_name == check_name
        )

    @staticmethod
    def _verify(
        payslip: PayslipExtraction,
        bank: BankStatementExtraction,
    ):
        return compare_financial_data(
            application_id=1,
            payslip_document_id=10,
            bank_statement_document_id=20,
            payslip=payslip,
            bank_statement=bank,
        )

    @staticmethod
    def _synthetic_payslip() -> PayslipExtraction:
        return PayslipExtraction(
            employee_name="Alex Morgan",
            employer_name="APEX TECHNOLOGIES INDIA PVT. LTD.",
            net_salary=Decimal("120800"),
            evidence=["Net salary: INR 120,800"],
        )

    @staticmethod
    def _synthetic_bank() -> BankStatementExtraction:
        return BankStatementExtraction(
            account_holder_name="Alex Morgan",
            opening_balance=Decimal("80000"),
            closing_balance=Decimal("115877"),
            statement_total_credits=Decimal("136275"),
            statement_total_debits=Decimal("100398"),
            transactions=[
                BankTransaction(
                    transaction_date="2026-10-01",
                    description="APEX TECHNOLOGIES PAYROLL",
                    credit=Decimal("120800"),
                    balance=Decimal("200800"),
                ),
                BankTransaction(
                    transaction_date="2026-10-10",
                    description="INTEREST CREDIT",
                    credit=Decimal("15475"),
                    balance=Decimal("216275"),
                ),
                BankTransaction(
                    transaction_date="2026-10-15",
                    description="LOAN EMI",
                    debit=Decimal("18500"),
                    balance=Decimal("197775"),
                ),
                BankTransaction(
                    transaction_date="2026-10-31",
                    description="OTHER DEBITS",
                    debit=Decimal("81898"),
                    balance=Decimal("115877"),
                ),
            ],
        )


if __name__ == "__main__":
    unittest.main()
