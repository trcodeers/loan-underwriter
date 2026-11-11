import unittest
from decimal import Decimal

from app.schemas.bank_statement import (
    BankStatementExtraction,
    BankTransaction,
)
from app.services.bank_transaction_classification import (
    classify_bank_statement_transactions,
)


class BankTransactionClassificationTests(unittest.TestCase):
    def test_synthetic_statement_and_common_categories(self) -> None:
        statement = BankStatementExtraction(
            transactions=[
                self._transaction(
                    "APEX TECHNOLOGIES PAYROLL",
                    credit="120800",
                ),
                self._transaction("NACH LOAN EMI PAYMENT", debit="18500"),
                self._transaction(
                    "INTERNAL TRANSFER TO OWN ACCOUNT",
                    debit="5000",
                ),
                self._transaction("UPI REFUND", credit="1250"),
                self._transaction("MONTHLY RENT PAYMENT", debit="25000"),
                self._transaction("ELECTRICITY BILL", debit="2200"),
                self._transaction("SUPERMARKET GROCERY", debit="1800"),
                self._transaction("E-COMMERCE APPAREL", debit="2600"),
                self._transaction("PHARMACY PURCHASE", debit="450"),
                self._transaction("ATM CASH WITHDRAWAL", debit="3000"),
                self._transaction("INSURANCE PREMIUM", debit="2100"),
            ],
        )
        original = statement.model_dump()

        classified = classify_bank_statement_transactions(statement)

        self.assertEqual(
            [item.category for item in classified],
            [
                "salary",
                "loan_emi",
                "internal_transfer",
                "refund_or_reversal",
                "rent",
                "utilities",
                "groceries",
                "shopping",
                "healthcare",
                "cash_withdrawal",
                "insurance",
            ],
        )
        self.assertEqual(statement.model_dump(), original)
        self.assertEqual(classify_bank_statement_transactions(statement), classified)
        self.assertEqual(classified[0].description, "APEX TECHNOLOGIES PAYROLL")
        self.assertEqual(classified[0].credit, Decimal("120800"))

    def test_ambiguous_direction_and_nach_are_uncertain(self) -> None:
        statement = BankStatementExtraction(
            transactions=[
                self._transaction("NACH DEBIT", debit="1200"),
                self._transaction("UPI PAYMENT", debit="500"),
                self._transaction("CREDIT", credit="9000"),
                self._transaction("UNRECOGNIZED", credit="10", debit="10"),
                self._transaction(None, debit="25"),
            ],
        )

        classified = classify_bank_statement_transactions(statement)

        self.assertTrue(
            all(item.category == "other_uncertain" for item in classified)
        )
        self.assertTrue(all(item.classification_reason for item in classified))

    def test_other_income_requires_explicit_income_evidence(self) -> None:
        statement = BankStatementExtraction(
            transactions=[
                self._transaction("INTEREST CREDIT", credit="125"),
                self._transaction("GENERIC TRANSFER", credit="500"),
            ],
        )

        classified = classify_bank_statement_transactions(statement)

        self.assertEqual(classified[0].category, "other_income")
        self.assertEqual(classified[1].category, "other_uncertain")

    @staticmethod
    def _transaction(
        description: str | None,
        credit: str | None = None,
        debit: str | None = None,
    ) -> BankTransaction:
        return BankTransaction(
            transaction_date="2026-10-01",
            description=description,
            credit=Decimal(credit) if credit is not None else None,
            debit=Decimal(debit) if debit is not None else None,
        )


if __name__ == "__main__":
    unittest.main()
