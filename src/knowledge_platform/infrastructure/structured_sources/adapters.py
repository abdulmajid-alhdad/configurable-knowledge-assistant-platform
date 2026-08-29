"""Metadata and read-only execution adapters for external structured sources."""

import sqlite3
from typing import Any

from sqlalchemy import Column, MetaData, Select, Table, and_, select

from knowledge_platform.modules.structured_retrieval.contracts import ValidatedStructuredPlan


class SQLiteStructuredSourceAdapter:
    def __init__(self, database: str) -> None:
        self.database = database

    def execute(self, plan: ValidatedStructuredPlan) -> tuple[dict[str, Any], ...]:
        if plan.policy.engine != "sqlite":
            raise ValueError("policy engine does not match SQLite adapter")
        uri = f"file:{self.database}?mode=ro"
        try:
            connection = sqlite3.connect(uri, uri=True)
            try:
                statement = compile_select(plan, MetaData())
                rows = connection.execute(str(statement), statement.compile().params).fetchall()
                keys = list(statement.selected_columns.keys())
                return tuple(dict(zip(keys, row, strict=True)) for row in rows)
            finally:
                connection.close()
        except sqlite3.Error as exc:
            raise RuntimeError("structured SQLite query failed") from exc


class PostgreSQLStructuredSourceAdapter:
    """Connection-bound contract; production connection provisioning is external."""

    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def execute(self, plan: ValidatedStructuredPlan) -> tuple[dict[str, Any], ...]:
        if plan.policy.engine != "postgresql":
            raise ValueError("policy engine does not match PostgreSQL adapter")
        try:
            result = self.connection.execute(compile_select(plan, MetaData()))
            return tuple(dict(row._mapping) for row in result)
        except Exception as exc:
            raise RuntimeError("structured PostgreSQL query failed") from exc


def compile_select(plan: ValidatedStructuredPlan, metadata: MetaData) -> Select[Any]:
    relation = Table(
        plan.plan.relation,
        metadata,
        *(Column(name) for name in plan.policy.allowed_columns[plan.plan.relation]),
        schema=plan.policy.allowed_schema if plan.policy.engine == "postgresql" else None,
    )
    columns = [relation.c[name] for name in plan.plan.fields]
    statement = select(*columns)
    conditions = []
    for field, operator, value in plan.plan.filters:
        column = relation.c[field]
        if operator == "=":
            parameter = column == value
        elif operator == "!=":
            parameter = column != value
        elif operator == ">":
            parameter = column > value
        elif operator == ">=":
            parameter = column >= value
        elif operator == "<":
            parameter = column < value
        else:
            parameter = column <= value
        conditions.append(parameter)
    if conditions:
        statement = statement.where(and_(*conditions))
    if plan.plan.order_by:
        statement = statement.order_by(*(relation.c[name] for name in plan.plan.order_by))
    return statement.limit(plan.plan.limit)
