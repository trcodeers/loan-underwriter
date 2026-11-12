from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from app.models.financial_analysis import FinancialAnalysis


def save_financial_analysis(
    db: Session,
    application_id: int,
    source_document_ids: list[int],
    calculation_inputs: dict[str, Any],
    calculation_results: dict[str, Any],
    calculation_version: str,
) -> FinancialAnalysis:
    record = FinancialAnalysis(
        application_id=application_id,
        source_document_ids=source_document_ids,
        calculation_inputs=_json_safe(calculation_inputs),
        calculation_results=_json_safe(calculation_results),
        calculation_version=calculation_version,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("Financial analysis JSON object keys must be strings")
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float):
        raise TypeError(
            "Financial analysis values must not use float; use Decimal "
            "to preserve precision"
        )
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(
        f"Unsupported financial analysis JSON value: {type(value).__name__}"
    )
