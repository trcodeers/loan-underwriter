from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class FinancialAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    analysis_id: int
    application_id: int
    source_document_ids: list[int]
    calculation_inputs: dict[str, Any]
    calculation_results: dict[str, Any]
    calculation_version: str
    created_at: datetime
