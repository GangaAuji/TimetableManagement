from __future__ import annotations

from ml.scoring.learned_predictor import predict_quality_score

SCORE_WEIGHTS = {
    "clash_risk": 0.35,
    "faculty_fatigue": 0.25,
    "room_overuse": 0.20,
    "student_load_imbalance": 0.20,
}


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _round2(value: float) -> float:
    return round(float(value), 2)


def score_from_features(features: dict) -> dict:
    """Apply weighted rule score and produce a breakdown and warnings."""

    clash_risk = _clamp01(features.get("clash_risk", 1.0))
    faculty_fatigue = _clamp01(features.get("faculty_fatigue", 1.0))
    room_overuse = _clamp01(features.get("room_overuse", 1.0))
    student_load_imbalance = _clamp01(features.get("student_load_imbalance", 1.0))

    quality_0_1 = (
        SCORE_WEIGHTS["clash_risk"] * (1.0 - clash_risk)
        + SCORE_WEIGHTS["faculty_fatigue"] * (1.0 - faculty_fatigue)
        + SCORE_WEIGHTS["room_overuse"] * (1.0 - room_overuse)
        + SCORE_WEIGHTS["student_load_imbalance"] * (1.0 - student_load_imbalance)
    )
    baseline_quality_score = _round2(quality_0_1 * 100.0)
    learned_quality_score, predictor_meta = predict_quality_score(features)
    quality_score = _round2(learned_quality_score) if learned_quality_score is not None else baseline_quality_score

    total_slots = int(features.get("total_slots", 0) or 0)
    unassigned_count = int(features.get("unassigned_count", 0) or 0)
    needs_room_count = int(features.get("needs_room_count", 0) or 0)
    max_room_share = _clamp01(features.get("max_room_share", 0.0))

    warnings: list[str] = []

    # Clash risk thresholds: aggressive for unresolved sessions.
    if clash_risk >= 0.45:
        warnings.append(
            f"High clash risk: {unassigned_count + needs_room_count} of {total_slots} slots need resolution."
        )
    elif clash_risk >= 0.25:
        warnings.append(
            f"Moderate clash risk: {unassigned_count + needs_room_count} slot(s) still need attention."
        )

    # Fatigue thresholds: keep sensitive but less noisy on balanced schedules.
    if faculty_fatigue >= 0.45:
        warnings.append("High faculty fatigue risk: concentrated back-to-back sessions detected.")
    elif faculty_fatigue >= 0.30:
        warnings.append("Moderate faculty fatigue risk on at least one day.")

    # Room overuse thresholds tuned to avoid over-alerting moderate concentration.
    if room_overuse >= 0.65:
        warnings.append(
            f"High room pressure: {needs_room_count} session(s) need room assignment and utilization is highly concentrated."
        )
    elif room_overuse >= 0.50:
        if needs_room_count > 0:
            warnings.append(
                f"Moderate room pressure: {needs_room_count} session(s) scheduled without preferred room assignment."
            )
        else:
            warnings.append(
                f"Moderate room concentration: one room handles about {_round2(max_room_share * 100)}% of assignments."
            )

    # Student load imbalance thresholds.
    if student_load_imbalance >= 0.45:
        warnings.append("High student load imbalance across working days.")
    elif student_load_imbalance >= 0.30:
        warnings.append("Moderate student load imbalance across working days.")

    day_density = features.get("day_density", {})
    if isinstance(day_density, dict) and day_density:
        most_loaded_day = max(day_density.keys(), key=lambda d: day_density[d].get("assigned", 0))
        least_loaded_day = min(day_density.keys(), key=lambda d: day_density[d].get("assigned", 0))
        if day_density[most_loaded_day].get("assigned", 0) - day_density[least_loaded_day].get("assigned", 0) >= 4:
            warnings.append(
                f"Load spread note: {most_loaded_day} is heavier than {least_loaded_day}."
            )

    return {
        "quality_score": quality_score,
        "baseline_quality_score": baseline_quality_score,
        "model_source": predictor_meta.get("model_source", "rule_fallback"),
        "model_meta": predictor_meta,
        "score_breakdown": {
            "clash_risk": _round2(clash_risk),
            "faculty_fatigue": _round2(faculty_fatigue),
            "room_overuse": _round2(room_overuse),
            "student_load_imbalance": _round2(student_load_imbalance),
        },
        "warnings": warnings,
    }
