"""Workspace-scoped Evaluation Control Plane delivery contracts."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from knowledge_platform.application.evaluation_catalog import SuiteArtifact, SuiteSummary
from knowledge_platform.application.evaluation_control import (
    EvaluationControlService,
    EvaluationRunDetail,
    EvaluationRunSummary,
)
from knowledge_platform.application.workspace_operational_state import (
    WorkspaceOperationalError,
)


class SuiteResponse(BaseModel):
    key: str
    name: str
    version: str
    case_count: int
    sha256: str
    evaluation_types: list[str]
    supported: bool


class SuiteCaseResponse(BaseModel):
    key: str
    evaluation_type: str
    question: str
    expected_outcome: str | None
    expected_source_ids: list[UUID]
    reference_answer: str | None


class SuiteDetailResponse(SuiteResponse):
    cases: list[SuiteCaseResponse]


class EvaluationRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite_key: str = Field(min_length=1, max_length=120)
    assistant_id: UUID


class EvaluationCaseResultResponse(BaseModel):
    case_key: str
    outcome_type: str
    passed: bool
    input: str | None = None
    expected_outcome: str | None = None
    expected_source_ids: list[UUID] = Field(default_factory=list)
    reference_answer: str | None = None
    actual: str | None = None
    actual_source_ids: list[UUID] = Field(default_factory=list)
    evidence_count: int = 0
    provenance_present: bool = False
    failure_category: str | None = None


class EvaluationRunSummaryResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    assistant_id: UUID | None
    assistant_name: str | None
    suite_key: str
    suite_version: str
    suite_sha256: str
    status: str
    case_count: int
    passed_count: int
    failed_count: int
    started_at: datetime | None
    completed_at: datetime | None
    failure_category: str | None


class EvaluationRunDetailResponse(EvaluationRunSummaryResponse):
    configuration: dict[str, object]
    results: list[EvaluationCaseResultResponse]


class EvaluationRunListResponse(BaseModel):
    items: list[EvaluationRunSummaryResponse]
    limit: int
    offset: int


def _suite_summary(value: SuiteSummary) -> SuiteResponse:
    return SuiteResponse(
        key=value.key,
        name=value.name,
        version=value.version,
        case_count=value.case_count,
        sha256=value.sha256,
        evaluation_types=list(value.evaluation_types),
        supported=value.supported,
    )


def _suite_detail(value: SuiteArtifact) -> SuiteDetailResponse:
    suite = value.suite
    types = sorted({case.type.value for case in suite.cases})
    return SuiteDetailResponse(
        key=suite.key,
        name=suite.name,
        version=suite.version,
        case_count=len(suite.cases),
        sha256=value.sha256,
        evaluation_types=types,
        supported="model_assisted" not in types,
        cases=[
            SuiteCaseResponse(
                key=case.key,
                evaluation_type=case.type.value,
                question=case.query,
                expected_outcome=case.expected_outcome,
                expected_source_ids=[source_id.value for source_id in case.expected_source_ids],
                reference_answer=case.reference_answer,
            )
            for case in suite.cases
        ],
    )


def _metric(value: EvaluationRunSummary, name: str) -> int:
    raw = value.summary_metrics.get(name, 0)
    return int(raw) if isinstance(raw, (int, float)) else 0


def _run_summary(value: EvaluationRunSummary) -> EvaluationRunSummaryResponse:
    return EvaluationRunSummaryResponse(
        id=value.id,
        workspace_id=value.workspace_id,
        assistant_id=value.assistant_id,
        assistant_name=value.assistant_name,
        suite_key=value.suite_key,
        suite_version=value.suite_version,
        suite_sha256=value.suite_hash,
        status=value.status,
        case_count=_metric(value, "case_count"),
        passed_count=_metric(value, "passed_count"),
        failed_count=_metric(value, "failed_count"),
        started_at=value.started_at or value.created_at,
        completed_at=value.completed_at,
        failure_category=value.failure_category,
    )


def _uuid_list(value: object) -> list[UUID]:
    if not isinstance(value, list):
        return []
    result: list[UUID] = []
    for item in value:
        try:
            result.append(UUID(str(item)))
        except (TypeError, ValueError):
            continue
    return result


def _run_detail(value: EvaluationRunDetail) -> EvaluationRunDetailResponse:
    summary = _run_summary(value.summary).model_dump()
    results = []
    for item in value.results:
        diagnostic = item.diagnostic
        evidence_count = diagnostic.get("evidence_count", 0)
        results.append(
            EvaluationCaseResultResponse(
                case_key=item.case_key,
                outcome_type=item.outcome_type,
                passed=item.passed,
                input=diagnostic.get("input") if isinstance(diagnostic.get("input"), str) else None,
                expected_outcome=(
                    diagnostic.get("expected_outcome")
                    if isinstance(diagnostic.get("expected_outcome"), str)
                    else None
                ),
                expected_source_ids=_uuid_list(diagnostic.get("expected_source_ids")),
                reference_answer=(
                    diagnostic.get("reference_answer")
                    if isinstance(diagnostic.get("reference_answer"), str)
                    else None
                ),
                actual=(
                    diagnostic.get("actual")
                    if isinstance(diagnostic.get("actual"), str)
                    else None
                ),
                actual_source_ids=_uuid_list(diagnostic.get("actual_source_ids")),
                evidence_count=(
                    int(evidence_count) if isinstance(evidence_count, (int, float)) else 0
                ),
                provenance_present=bool(diagnostic.get("provenance_present", False)),
                failure_category=(
                    diagnostic.get("failure_category")
                    if isinstance(diagnostic.get("failure_category"), str)
                    else None
                ),
            )
        )
    return EvaluationRunDetailResponse(
        **summary,
        configuration=value.configuration_snapshot,
        results=results,
    )


def create_evaluation_router(service: EvaluationControlService) -> APIRouter:
    router = APIRouter(prefix="/api/workspaces/{workspace_id}/evaluation")

    @router.get("/suites", response_model=list[SuiteResponse])
    def list_suites(workspace_id: UUID, request: Request) -> list[SuiteResponse]:
        return [
            _suite_summary(summary)
            for summary in service.list_suites(request.state.user.id, workspace_id)
        ]

    @router.get("/suites/{suite_key}", response_model=SuiteDetailResponse)
    def get_suite(
        workspace_id: UUID, suite_key: str, request: Request
    ) -> SuiteDetailResponse:
        return _suite_detail(
            service.get_suite(request.state.user.id, workspace_id, suite_key)
        )

    @router.post(
        "/runs", response_model=EvaluationRunDetailResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_run(
        workspace_id: UUID, payload: EvaluationRunRequest, request: Request
    ) -> EvaluationRunDetailResponse:
        try:
            return _run_detail(
                service.create_run(
                    request.state.user.id,
                    workspace_id,
                    suite_key=payload.suite_key,
                    assistant_id=payload.assistant_id,
                    request_id=request.headers.get("x-request-id"),
                )
            )
        except WorkspaceOperationalError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get("/runs", response_model=EvaluationRunListResponse)
    def list_runs(
        workspace_id: UUID,
        request: Request,
        suite_key: str | None = Query(default=None, min_length=1, max_length=120),
        assistant_id: UUID | None = None,
        run_status: Literal["created", "running", "completed", "failed"] | None = Query(
            default=None, alias="status"
        ),
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> EvaluationRunListResponse:
        items = service.list_runs(
            request.state.user.id,
            workspace_id,
            suite_key=suite_key,
            assistant_id=assistant_id,
            status=run_status,
            limit=limit,
            offset=offset,
        )
        return EvaluationRunListResponse(
            items=[_run_summary(item) for item in items], limit=limit, offset=offset
        )

    @router.get("/runs/{run_id}", response_model=EvaluationRunDetailResponse)
    def get_run(
        workspace_id: UUID, run_id: UUID, request: Request
    ) -> EvaluationRunDetailResponse:
        return _run_detail(
            service.get_run(request.state.user.id, workspace_id, run_id)
        )

    @router.post(
        "/runs/{run_id}/rerun",
        response_model=EvaluationRunDetailResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def rerun(
        workspace_id: UUID, run_id: UUID, request: Request
    ) -> EvaluationRunDetailResponse:
        try:
            return _run_detail(
                service.rerun(
                    request.state.user.id,
                    workspace_id,
                    run_id,
                    request_id=request.headers.get("x-request-id"),
                )
            )
        except WorkspaceOperationalError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return router
