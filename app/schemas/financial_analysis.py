from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FinancialCalculationRequest(BaseModel):
    max_foir_percent: Decimal | None = Field(default=None, gt=0, le=100)
    proposed_annual_interest_rate: Decimal | None = Field(default=None, ge=0)
    proposed_tenure_months: int | None = Field(default=None, gt=0)
    minimum_monthly_reserve: Decimal | None = Field(default=None, ge=0)


class FinancialAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    analysis_id: int
    application_id: int
    source_document_ids: list[int]
    calculation_inputs: dict[str, Any]
    calculation_results: dict[str, Any]
    calculation_version: str
    created_at: datetime
