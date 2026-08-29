from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class EvaluationBase(DeclarativeBase):
    pass

class EvaluationRunRecord(EvaluationBase):
    __tablename__ = "evaluation_runs"
    __table_args__ = (
        CheckConstraint(
            "lifecycle IN ('created','running','completed','failed')",
            name="evaluation_runs_lifecycle",
        ),
        {"schema": "evaluation"},
    )
    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    suite_key: Mapped[str] = mapped_column(Text, nullable=False)
    suite_version: Mapped[str] = mapped_column(Text, nullable=False)
    suite_hash: Mapped[str] = mapped_column(Text, nullable=False)
    lifecycle: Mapped[str] = mapped_column(Text, nullable=False)
    configuration_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    summary_metrics: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)

class EvaluationResultRecord(EvaluationBase):
    __tablename__ = "evaluation_results"
    __table_args__ = ({"schema": "evaluation"},)
    run_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("evaluation.evaluation_runs.id"),
        primary_key=True,
    )
    case_key: Mapped[str] = mapped_column(Text, primary_key=True)
    outcome_type: Mapped[str] = mapped_column(Text, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    diagnostic: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
