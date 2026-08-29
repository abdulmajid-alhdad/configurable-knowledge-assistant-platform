"""Policy validation producing a structurally trusted plan."""

from .contracts import StructuredQueryPlan, StructuredSourcePolicy, ValidatedStructuredPlan


class PolicyDeniedError(ValueError):
    pass


def validate_plan(
    plan: StructuredQueryPlan, policy: StructuredSourcePolicy
) -> ValidatedStructuredPlan:
    if plan.source_id != policy.source_id:
        raise PolicyDeniedError("source is not eligible")
    if plan.relation not in policy.allowed_relations:
        raise PolicyDeniedError("relation is not allowed")
    allowed = policy.allowed_columns.get(plan.relation, frozenset())
    fields = set(plan.fields)
    filter_fields = {item[0] for item in plan.filters}
    if not fields or not fields.issubset(allowed) or not filter_fields.issubset(allowed):
        raise PolicyDeniedError("column is not allowed")
    if not set(plan.order_by).issubset(allowed):
        raise PolicyDeniedError("sort column is not allowed")
    if fields & policy.restricted_columns or filter_fields & policy.restricted_columns:
        raise PolicyDeniedError("restricted column requested")
    if plan.limit <= 0 or plan.limit > policy.max_rows:
        raise PolicyDeniedError("query limit exceeds policy")
    if any(op not in ("=", "!=", ">", ">=", "<", "<=") for _, op, _ in plan.filters):
        raise PolicyDeniedError("unsupported filter operator")
    return ValidatedStructuredPlan(plan=plan, policy=policy)
