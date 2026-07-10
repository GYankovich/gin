from app.modules.recommendations.rules import _dedupe_conflicting_field_changes
from app.modules.recommendations.schemas import (
    RecommendationCategory,
    RecommendationItem,
    RecommendationSeverity,
    SuggestedChange,
)


def _item(item_id: str, severity: RecommendationSeverity, *changes: SuggestedChange) -> RecommendationItem:
    return RecommendationItem(
        id=item_id,
        category=RecommendationCategory.RISK,
        severity=severity,
        title=item_id,
        message="test",
        suggested_changes=list(changes),
        evidence={},
    )


def test_dedupe_keeps_higher_priority_field_change():
    items = [
        _item(
            "heuristic-dd",
            RecommendationSeverity.INFO,
            SuggestedChange(
                path="risk.max_position_percent",
                current_value=15,
                suggested_value=12,
            ),
        ),
        _item(
            "rule-dd",
            RecommendationSeverity.WARNING,
            SuggestedChange(
                path="risk.max_position_percent",
                current_value=15,
                suggested_value=9,
            ),
        ),
    ]
    out = _dedupe_conflicting_field_changes(items)
    by_id = {it.id: it for it in out}
    assert len(by_id["rule-dd"].suggested_changes) == 1
    assert by_id["rule-dd"].suggested_changes[0].suggested_value == 9
    assert by_id["heuristic-dd"].suggested_changes == []


def test_dedupe_prefers_rule_engine_on_equal_severity():
    items = [
        _item(
            "heuristic",
            RecommendationSeverity.WARNING,
            SuggestedChange(path="risk.take_profit_percent", current_value=3, suggested_value=4),
        ),
        _item(
            "rule-tp",
            RecommendationSeverity.WARNING,
            SuggestedChange(path="risk.take_profit_percent", current_value=3, suggested_value=5),
        ),
    ]
    out = _dedupe_conflicting_field_changes(items)
    by_id = {it.id: it for it in out}
    assert len(by_id["rule-tp"].suggested_changes) == 1
    assert by_id["heuristic"].suggested_changes == []
