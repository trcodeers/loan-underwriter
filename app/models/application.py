from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from sqlalchemy.orm import relationship

class LoanApplication(Base):
    __tablename__ = "loan_applications"

    documents = relationship(
        "Document",
        back_populates="application",
        cascade="all, delete-orphan",
    )
    
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    applicant_name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    requested_loan_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    loan_purpose: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default="documents_pending",
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )