"""Safe evaluation suite inspection endpoints."""
from fastapi import APIRouter
from pydantic import BaseModel

from knowledge_platform.application.evaluation_catalog import EvaluationCatalogService


class SuiteResponse(BaseModel):
    key: str
    name: str
    version: str
    case_count: int
    sha256: str


def create_evaluation_router(service: EvaluationCatalogService) -> APIRouter:
    router = APIRouter(prefix="/api/evaluation")

    @router.get("/suites", response_model=list[SuiteResponse])
    def list_suites() -> list[SuiteResponse]:
        return [
            SuiteResponse(
                key=summary.key, name=summary.name, version=summary.version,
                case_count=summary.case_count, sha256=summary.sha256,
            )
            for summary in service.list_suites()
        ]

    return router
