"""PostgreSQL adapter for workspace-scoped evaluation run history."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, sessionmaker

from knowledge_platform.application.evaluation import EvaluationReport, EvaluationResult
from knowledge_platform.application.evaluation_catalog import SuiteArtifact
from knowledge_platform.application.evaluation_control import (
    EvaluationAssistant,
    EvaluationCaseResultView,
    EvaluationRunDetail,
    EvaluationRunSummary,
)
from knowledge_platform.modules.evaluation.domain.contracts import EvaluationRun


class SqlAlchemyEvaluationStore:
    """Keeps each state transition and its audit event in one transaction."""

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    @contextmanager
    def _tx(self, actor: UUID, workspace_id: UUID) -> Iterator[Session]:
        with self._sessions.begin() as session:
            session.execute(
                text("select set_config('app.user_id', :value, true)"),
                {"value": str(actor)},
            )
            session.execute(
                text("select set_config('app.workspace_id', :value, true)"),
                {"value": str(workspace_id)},
            )
            yield session

    @staticmethod
    def _rowcount(value: object) -> int:
        return cast(CursorResult[Any], value).rowcount

    @staticmethod
    def _audit(
        session: Session,
        workspace_id: UUID,
        *,
        action: str,
        run_id: UUID | None,
        outcome: str,
        request_id: str | None,
        metadata: dict[str, object],
    ) -> None:
        session.execute(
            text("""
                select platform.append_audit_event(
                  :workspace,:action,'evaluation_run',:run_id,:outcome,
                  :request_id,cast(:metadata as jsonb))
            """),
            {
                "workspace": workspace_id,
                "action": action,
                "run_id": run_id,
                "outcome": outcome,
                "request_id": request_id or "",
                "metadata": json.dumps(metadata),
            },
        )

    def get_assistant(
        self, actor: UUID, workspace_id: UUID, assistant_id: UUID
    ) -> EvaluationAssistant | None:
        with self._tx(actor, workspace_id) as session:
            row = session.execute(
                text("""
                    select id,name from platform.assistants
                    where id=:assistant and workspace_id=:workspace
                """),
                {"assistant": assistant_id, "workspace": workspace_id},
            ).mappings().one_or_none()
        if row is None:
            return None
        return EvaluationAssistant(id=cast(UUID, row["id"]), name=str(row["name"]))

    def create_started_run(
        self,
        actor: UUID,
        workspace_id: UUID,
        assistant: EvaluationAssistant,
        artifact: SuiteArtifact,
        run: EvaluationRun,
        *,
        request_id: str | None,
        rerun_of: UUID | None,
    ) -> None:
        now = datetime.now(UTC)
        configuration: dict[str, object] = {
            "suite_name": artifact.suite.name,
            "case_count": len(artifact.suite.cases),
            "evaluation_types": sorted(
                {case.type.value for case in artifact.suite.cases}
            ),
            "assistant_name": assistant.name,
        }
        if rerun_of is not None:
            configuration["rerun_of"] = str(rerun_of)
        with self._tx(actor, workspace_id) as session:
            session.execute(
                text("""
                    insert into evaluation.evaluation_runs (
                      id,workspace_id,assistant_id,requested_by,suite_key,
                      suite_version,suite_hash,lifecycle,configuration_snapshot,
                      summary_metrics,created_at,started_at
                    ) values (
                      :id,:workspace,:assistant,:actor,:suite_key,:suite_version,
                      :suite_hash,'running',cast(:configuration as jsonb),
                      '{}'::jsonb,:created_at,:started_at
                    )
                """),
                {
                    "id": run.id.value,
                    "workspace": workspace_id,
                    "assistant": assistant.id,
                    "actor": actor,
                    "suite_key": artifact.suite.key,
                    "suite_version": artifact.suite.version,
                    "suite_hash": artifact.sha256,
                    "configuration": json.dumps(configuration),
                    "created_at": now,
                    "started_at": now,
                },
            )
            self._audit(
                session,
                workspace_id,
                action=(
                    "evaluation.rerun_requested"
                    if rerun_of is not None
                    else "evaluation.run_requested"
                ),
                run_id=run.id.value,
                outcome="succeeded",
                request_id=request_id,
                metadata={
                    "suite_key": artifact.suite.key,
                    "suite_version": artifact.suite.version,
                    "assistant_id": str(assistant.id),
                    **({"source_run_id": str(rerun_of)} if rerun_of else {}),
                },
            )
            self._audit(
                session,
                workspace_id,
                action="evaluation.run_started",
                run_id=run.id.value,
                outcome="succeeded",
                request_id=request_id,
                metadata={
                    "suite_key": artifact.suite.key,
                    "assistant_id": str(assistant.id),
                },
            )

    @staticmethod
    def _diagnostic(result: EvaluationResult) -> dict[str, object]:
        return {
            "input": result.input_query,
            "expected_outcome": result.expected_outcome,
            "expected_source_ids": list(result.expected_source_ids),
            "reference_answer": result.reference_answer,
            "actual": result.actual_text,
            "actual_source_ids": list(result.actual_source_ids),
            "evidence_count": result.evidence_count,
            "provenance_present": result.provenance_present,
            "failure_category": result.failure_category,
        }

    @classmethod
    def _insert_results(
        cls, session: Session, run_id: UUID, report: EvaluationReport
    ) -> None:
        for result in report.results:
            session.execute(
                text("""
                    insert into evaluation.evaluation_results (
                      run_id,case_key,outcome_type,passed,diagnostic
                    ) values (
                      :run_id,:case_key,:outcome_type,:passed,cast(:diagnostic as jsonb)
                    )
                """),
                {
                    "run_id": run_id,
                    "case_key": result.case_key,
                    "outcome_type": result.outcome_type,
                    "passed": result.passed,
                    "diagnostic": json.dumps(cls._diagnostic(result)),
                },
            )

    def complete_run(
        self,
        actor: UUID,
        workspace_id: UUID,
        report: EvaluationReport,
        *,
        request_id: str | None,
    ) -> None:
        run_id = report.run.id.value
        with self._tx(actor, workspace_id) as session:
            self._insert_results(session, run_id, report)
            changed = self._rowcount(
                session.execute(
                    text("""
                        update evaluation.evaluation_runs
                        set lifecycle='completed',summary_metrics=cast(:metrics as jsonb),
                            completed_at=:completed,failure_category=null
                        where id=:id and workspace_id=:workspace and lifecycle='running'
                    """),
                    {
                        "metrics": json.dumps(report.metrics),
                        "completed": datetime.now(UTC),
                        "id": run_id,
                        "workspace": workspace_id,
                    },
                )
            )
            if changed != 1:
                raise RuntimeError("evaluation run state conflict")
            self._audit(
                session,
                workspace_id,
                action="evaluation.run_completed",
                run_id=run_id,
                outcome="succeeded",
                request_id=request_id,
                metadata={
                    "passed_count": int(report.metrics["passed_count"]),
                    "case_count": int(report.metrics["case_count"]),
                },
            )

    def fail_run(
        self,
        actor: UUID,
        workspace_id: UUID,
        report: EvaluationReport,
        *,
        request_id: str | None,
    ) -> None:
        run_id = report.run.id.value
        failure = report.failure_category or "EVALUATION_EXECUTION_FAILED"
        with self._tx(actor, workspace_id) as session:
            self._insert_results(session, run_id, report)
            changed = self._rowcount(
                session.execute(
                    text("""
                        update evaluation.evaluation_runs
                        set lifecycle='failed',summary_metrics=cast(:metrics as jsonb),
                            completed_at=:completed,failure_category=:failure
                        where id=:id and workspace_id=:workspace and lifecycle='running'
                    """),
                    {
                        "metrics": json.dumps(report.metrics),
                        "completed": datetime.now(UTC),
                        "failure": failure,
                        "id": run_id,
                        "workspace": workspace_id,
                    },
                )
            )
            if changed != 1:
                raise RuntimeError("evaluation run state conflict")
            self._audit(
                session,
                workspace_id,
                action="evaluation.run_failed",
                run_id=run_id,
                outcome="failed",
                request_id=request_id,
                metadata={"reason": failure},
            )

    def audit_denied(
        self,
        actor: UUID,
        workspace_id: UUID,
        *,
        action: str,
        reason: str,
        suite_key: str | None = None,
        assistant_id: UUID | None = None,
        request_id: str | None = None,
    ) -> None:
        metadata: dict[str, object] = {"reason": reason}
        if suite_key:
            metadata["suite_key"] = suite_key
        if assistant_id:
            metadata["assistant_id"] = str(assistant_id)
        with self._tx(actor, workspace_id) as session:
            self._audit(
                session,
                workspace_id,
                action=action,
                run_id=None,
                outcome="denied",
                request_id=request_id,
                metadata=metadata,
            )

    @staticmethod
    def _summary(row: Any) -> EvaluationRunSummary:
        return EvaluationRunSummary(
            id=cast(UUID, row["id"]),
            workspace_id=cast(UUID, row["workspace_id"]),
            assistant_id=cast(UUID | None, row["assistant_id"]),
            assistant_name=cast(str | None, row["assistant_name"]),
            suite_key=str(row["suite_key"]),
            suite_version=str(row["suite_version"]),
            suite_hash=str(row["suite_hash"]),
            status=str(row["lifecycle"]),
            summary_metrics=dict(row["summary_metrics"] or {}),
            created_at=cast(datetime | None, row["created_at"]),
            started_at=cast(datetime | None, row["started_at"]),
            completed_at=cast(datetime | None, row["completed_at"]),
            failure_category=cast(str | None, row["failure_category"]),
        )

    def list_runs(
        self,
        actor: UUID,
        workspace_id: UUID,
        *,
        suite_key: str | None,
        assistant_id: UUID | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> list[EvaluationRunSummary]:
        with self._tx(actor, workspace_id) as session:
            rows = session.execute(
                text("""
                    select r.id,r.workspace_id,r.assistant_id,a.name assistant_name,
                           r.suite_key,r.suite_version,r.suite_hash,r.lifecycle,
                           r.summary_metrics,r.created_at,r.started_at,r.completed_at,
                           r.failure_category
                    from evaluation.evaluation_runs r
                    left join platform.assistants a
                      on a.id=r.assistant_id and a.workspace_id=r.workspace_id
                    where r.workspace_id=:workspace
                      and (cast(:suite_key as text) is null
                           or r.suite_key=cast(:suite_key as text))
                      and (cast(:assistant_id as uuid) is null
                           or r.assistant_id=cast(:assistant_id as uuid))
                      and (cast(:status as text) is null
                           or r.lifecycle=cast(:status as text))
                    order by coalesce(r.started_at,r.created_at) desc nulls last,r.id desc
                    limit :limit offset :offset
                """),
                {
                    "workspace": workspace_id,
                    "suite_key": suite_key,
                    "assistant_id": str(assistant_id) if assistant_id else None,
                    "status": status,
                    "limit": limit,
                    "offset": offset,
                },
            ).mappings().all()
        return [self._summary(row) for row in rows]

    def get_run(
        self, actor: UUID, workspace_id: UUID, run_id: UUID
    ) -> EvaluationRunDetail | None:
        with self._tx(actor, workspace_id) as session:
            row = session.execute(
                text("""
                    select r.id,r.workspace_id,r.assistant_id,a.name assistant_name,
                           r.suite_key,r.suite_version,r.suite_hash,r.lifecycle,
                           r.configuration_snapshot,r.summary_metrics,r.created_at,
                           r.started_at,r.completed_at,r.failure_category
                    from evaluation.evaluation_runs r
                    left join platform.assistants a
                      on a.id=r.assistant_id and a.workspace_id=r.workspace_id
                    where r.id=:id and r.workspace_id=:workspace
                """),
                {"id": run_id, "workspace": workspace_id},
            ).mappings().one_or_none()
            if row is None:
                return None
            results = session.execute(
                text("""
                    select case_key,outcome_type,passed,diagnostic
                    from evaluation.evaluation_results
                    where run_id=:run order by case_key
                """),
                {"run": run_id},
            ).mappings().all()
        return EvaluationRunDetail(
            summary=self._summary(row),
            configuration_snapshot=dict(row["configuration_snapshot"] or {}),
            results=tuple(
                EvaluationCaseResultView(
                    case_key=str(result["case_key"]),
                    outcome_type=str(result["outcome_type"]),
                    passed=bool(result["passed"]),
                    diagnostic=dict(result["diagnostic"] or {}),
                )
                for result in results
            ),
        )
