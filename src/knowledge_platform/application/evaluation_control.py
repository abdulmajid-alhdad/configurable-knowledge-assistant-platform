"""Workspace-scoped operational evaluation orchestration."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from knowledge_platform.application.access_control import AccessControlPort
from knowledge_platform.application.evaluation import (
    EvaluationExecutionFailed,
    EvaluationExecutionPort,
    EvaluationReport,
    EvaluationRunner,
)
from knowledge_platform.application.evaluation_catalog import (
    EvaluationCatalogService,
    SuiteArtifact,
    SuiteSummary,
    suite_is_supported,
)
from knowledge_platform.modules.access_control.domain import Permission
from knowledge_platform.modules.evaluation.domain.contracts import EvaluationRun


class EvaluationErrorCode(StrEnum):
    SUITE_NOT_FOUND = "EVALUATION_SUITE_NOT_FOUND"
    RUN_NOT_FOUND = "EVALUATION_RUN_NOT_FOUND"
    ASSISTANT_NOT_FOUND = "EVALUATION_ASSISTANT_NOT_FOUND"
    MODE_UNSUPPORTED = "EVALUATION_MODE_UNSUPPORTED"
    EXECUTION_FAILED = "EVALUATION_EXECUTION_FAILED"


class EvaluationControlError(RuntimeError):
    """Stable, browser-safe evaluation application failure."""

    def __init__(
        self, code: EvaluationErrorCode, *, run_id: UUID | None = None
    ) -> None:
        super().__init__(code.value)
        self.code = code
        self.run_id = run_id


@dataclass(frozen=True, slots=True)
class EvaluationAssistant:
    id: UUID
    name: str


@dataclass(frozen=True, slots=True)
class EvaluationRunSummary:
    id: UUID
    workspace_id: UUID
    assistant_id: UUID | None
    assistant_name: str | None
    suite_key: str
    suite_version: str
    suite_hash: str
    status: str
    summary_metrics: dict[str, object]
    created_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    failure_category: str | None


@dataclass(frozen=True, slots=True)
class EvaluationCaseResultView:
    case_key: str
    outcome_type: str
    passed: bool
    diagnostic: dict[str, object]


@dataclass(frozen=True, slots=True)
class EvaluationRunDetail:
    summary: EvaluationRunSummary
    configuration_snapshot: dict[str, object]
    results: tuple[EvaluationCaseResultView, ...]


class EvaluationStorePort(Protocol):
    def get_assistant(
        self, actor: UUID, workspace_id: UUID, assistant_id: UUID
    ) -> EvaluationAssistant | None: ...

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
    ) -> None: ...

    def complete_run(
        self,
        actor: UUID,
        workspace_id: UUID,
        report: EvaluationReport,
        *,
        request_id: str | None,
    ) -> None: ...

    def fail_run(
        self,
        actor: UUID,
        workspace_id: UUID,
        report: EvaluationReport,
        *,
        request_id: str | None,
    ) -> None: ...

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
    ) -> None: ...

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
    ) -> list[EvaluationRunSummary]: ...

    def get_run(
        self, actor: UUID, workspace_id: UUID, run_id: UUID
    ) -> EvaluationRunDetail | None: ...


class EvaluationExecutionFactory(Protocol):
    def build(
        self, workspace_id: UUID, assistant_id: UUID
    ) -> EvaluationExecutionPort: ...


class EvaluationWorkspaceStatePort(Protocol):
    def require_ai_execution(self, user_id: UUID, workspace_id: UUID) -> None: ...


class EvaluationControlService:
    """Coordinates authz, immutable suites, execution, history, and audit."""

    def __init__(
        self,
        *,
        access: AccessControlPort,
        catalog: EvaluationCatalogService,
        store: EvaluationStorePort,
        execution_factory: EvaluationExecutionFactory,
        workspace_state: EvaluationWorkspaceStatePort,
    ) -> None:
        self._access = access
        self._catalog = catalog
        self._store = store
        self._execution_factory = execution_factory
        self._workspace_state = workspace_state

    def list_suites(self, actor: UUID, workspace_id: UUID) -> list[SuiteSummary]:
        self._access.require(actor, workspace_id, Permission.EVALUATION_READ)
        return self._catalog.list_suites()

    def get_suite(
        self, actor: UUID, workspace_id: UUID, suite_key: str
    ) -> SuiteArtifact:
        self._access.require(actor, workspace_id, Permission.EVALUATION_READ)
        artifact = self._catalog.get_suite(suite_key)
        if artifact is None:
            raise EvaluationControlError(EvaluationErrorCode.SUITE_NOT_FOUND)
        return artifact

    def create_run(
        self,
        actor: UUID,
        workspace_id: UUID,
        *,
        suite_key: str,
        assistant_id: UUID,
        request_id: str | None = None,
        rerun_of: UUID | None = None,
    ) -> EvaluationRunDetail:
        self._access.require(actor, workspace_id, Permission.EVALUATION_RUN)
        self._workspace_state.require_ai_execution(actor, workspace_id)
        artifact = self._catalog.get_suite(suite_key)
        if artifact is None:
            raise EvaluationControlError(EvaluationErrorCode.SUITE_NOT_FOUND)
        if not suite_is_supported(artifact.suite):
            self._store.audit_denied(
                actor,
                workspace_id,
                action="evaluation.run_denied",
                reason=EvaluationErrorCode.MODE_UNSUPPORTED.value,
                suite_key=artifact.suite.key,
                assistant_id=assistant_id,
                request_id=request_id,
            )
            raise EvaluationControlError(EvaluationErrorCode.MODE_UNSUPPORTED)
        assistant = self._store.get_assistant(actor, workspace_id, assistant_id)
        if assistant is None:
            self._store.audit_denied(
                actor,
                workspace_id,
                action="evaluation.run_denied",
                reason=EvaluationErrorCode.ASSISTANT_NOT_FOUND.value,
                suite_key=artifact.suite.key,
                assistant_id=assistant_id,
                request_id=request_id,
            )
            raise EvaluationControlError(EvaluationErrorCode.ASSISTANT_NOT_FOUND)

        run = EvaluationRun.create(suite=artifact.suite).start()
        self._store.create_started_run(
            actor,
            workspace_id,
            assistant,
            artifact,
            run,
            request_id=request_id,
            rerun_of=rerun_of,
        )
        runner = EvaluationRunner(
            self._execution_factory.build(workspace_id, assistant_id)
        )
        try:
            report = runner.run_started(run)
        except EvaluationExecutionFailed as error:
            self._store.fail_run(
                actor,
                workspace_id,
                error.report,
                request_id=request_id,
            )
            raise EvaluationControlError(
                EvaluationErrorCode.EXECUTION_FAILED, run_id=run.id.value
            ) from None
        self._store.complete_run(
            actor, workspace_id, report, request_id=request_id
        )
        detail = self._store.get_run(actor, workspace_id, run.id.value)
        if detail is None:
            raise EvaluationControlError(EvaluationErrorCode.RUN_NOT_FOUND)
        return detail

    def list_runs(
        self,
        actor: UUID,
        workspace_id: UUID,
        *,
        suite_key: str | None = None,
        assistant_id: UUID | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EvaluationRunSummary]:
        self._access.require(actor, workspace_id, Permission.EVALUATION_READ)
        return self._store.list_runs(
            actor,
            workspace_id,
            suite_key=suite_key,
            assistant_id=assistant_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    def get_run(
        self, actor: UUID, workspace_id: UUID, run_id: UUID
    ) -> EvaluationRunDetail:
        self._access.require(actor, workspace_id, Permission.EVALUATION_READ)
        detail = self._store.get_run(actor, workspace_id, run_id)
        if detail is None:
            raise EvaluationControlError(EvaluationErrorCode.RUN_NOT_FOUND)
        return detail

    def rerun(
        self,
        actor: UUID,
        workspace_id: UUID,
        run_id: UUID,
        *,
        request_id: str | None = None,
    ) -> EvaluationRunDetail:
        self._access.require(actor, workspace_id, Permission.EVALUATION_RUN)
        original = self._store.get_run(actor, workspace_id, run_id)
        if original is None or original.summary.assistant_id is None:
            raise EvaluationControlError(EvaluationErrorCode.RUN_NOT_FOUND)
        return self.create_run(
            actor,
            workspace_id,
            suite_key=original.summary.suite_key,
            assistant_id=original.summary.assistant_id,
            request_id=request_id,
            rerun_of=run_id,
        )
