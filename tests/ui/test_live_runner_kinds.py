"""Coverage statuses must not fail plan validation when used as a kind."""

from ui.api.live_runner import _coerce_recommendation_kinds


def test_gap_kind_maps_to_orchestrate() -> None:
    plan = {
        "recommendations": [
            {"id": "R-003", "kind": "orchestrate"},
            {"id": "R-004", "kind": "gap"},
            {"id": "R-005", "kind": "redundant"},
        ]
    }
    coerced = _coerce_recommendation_kinds(plan)
    kinds = [rec["kind"] for rec in coerced["recommendations"]]
    assert kinds == ["orchestrate", "orchestrate", "consolidate"]
