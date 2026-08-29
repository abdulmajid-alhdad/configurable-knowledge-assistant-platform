from sqlalchemy.orm import Session

from knowledge_platform.application.evaluation import EvaluationReport
from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId

from .models import EvaluationResultRecord, EvaluationRunRecord


class EvaluationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_report(self, report: EvaluationReport, *, workspace_id: WorkspaceId) -> None:
        run = report.run
        self._session.add(EvaluationRunRecord(
            id=run.id.value, workspace_id=workspace_id.value, suite_key=run.suite.key,
            suite_version=run.suite.version, suite_hash="", lifecycle=run.lifecycle.value,
            configuration_snapshot={}, summary_metrics=report.metrics,
        ))
        for result in report.results:
            self._session.add(EvaluationResultRecord(
                run_id=run.id.value, case_key=result.case_key,
                outcome_type=result.outcome_type, passed=result.passed,
                diagnostic={"evidence_count": result.evidence_count},
            ))
