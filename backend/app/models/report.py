from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Report(Base):
    """Metadata for a generated diagnostic report; the file itself is written
    to disk (see app.services.reports) and referenced by file_path."""
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    diagnostic_run_id: Mapped[int | None] = mapped_column(ForeignKey("diagnostic_runs.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    format: Mapped[str] = mapped_column(String(10), nullable=False)  # pdf | csv | json
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
