from __future__ import annotations

from ml_models.features.timetable_features import extract_timetable_features
from ml_models.scoring.rule_scorer import score_from_features


def score_timetable_candidate(
    assigned: list[dict],
    unassigned: list[dict],
    proxy_suggestions: list[dict],
    needs_room: list[dict],
    slots_per_day: dict[str, int] | None = None,
    rules: dict | None = None,
) -> dict:
    """Return quality_score (0-100), score_breakdown, and warning list.

    `rules` (services/timetable/rules.py) sets the fatigue thresholds - hours per day and consecutive
    hours - so the quality model agrees with the solvers; without it the historical thresholds apply.
    """

    features = extract_timetable_features(
        assigned=assigned,
        unassigned=unassigned,
        proxy_suggestions=proxy_suggestions,
        needs_room=needs_room,
        slots_per_day=slots_per_day,
        rules=rules,
    )
    score = score_from_features(features)
    return {
        **score,
        "features": features,
    }
