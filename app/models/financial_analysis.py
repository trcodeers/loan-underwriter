from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class FinancialAnalysis(Base):
    __tablename__ = "financial_analyses"
    __table_args__ = (
        Index(
            "ix_financial_analyses_application_created_at",
            "application_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("loan_applications.id"),
        nullable=False,
    )
    source_document_ids: Mapped[list[int]] = mapped_column(
        JSON,
        nullable=False,
    )
    calculation_inputs: Mapped[dict] = mapped_column(JSON, nullable=False)
    calculation_results: Mapped[dict] = mapped_column(JSON, nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    application = relationship(
        "LoanApplication",
        back_populates="financial_analyses",
    )
