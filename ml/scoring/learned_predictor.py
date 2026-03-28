from __future__ import annotations

import json
import math
import os
from typing import Iterable

from database import get_db_connection

# Ordered feature list used by both training and inference.
_FEATURE_NAMES = [
    "clash_risk",
    "faculty_fatigue",
    "room_overuse",
    "student_load_imbalance",
]

# Module-level cache to avoid repeated disk reads during high request throughput.
_MODEL_CACHE: dict | None = None
_MODEL_CACHE_PATH: str | None = None
_MODEL_CACHE_MTIME: float | None = None


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _sigmoid(value: float) -> float:
    # Guard against overflow while keeping deterministic output.
    if value >= 40:
        return 1.0
    if value <= -40:
        return 0.0
    return 1.0 / (1.0 + math.exp(-value))


def _default_model_path() -> str:
    # Keep model artifact inside repository for simple deployment.
    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "models", "timetable_quality_model.json")
    )


def _feature_vector(features: dict) -> list[float]:
    # Risk features are already normalized to 0..1 by feature extraction.
    return [_clamp01(features.get(name, 1.0)) for name in _FEATURE_NAMES]


def _standardize(values: Iterable[float], mean: float, std: float) -> list[float]:
    denom = std if std > 1e-9 else 1.0
    return [(float(v) - mean) / denom for v in values]


def _load_model(model_path: str | None = None) -> dict | None:
    global _MODEL_CACHE, _MODEL_CACHE_PATH, _MODEL_CACHE_MTIME

    path = os.path.abspath(model_path or _default_model_path())
    if not os.path.exists(path):
        return None

    mtime = os.path.getmtime(path)
    if (
        _MODEL_CACHE is not None
        and _MODEL_CACHE_PATH == path
        and _MODEL_CACHE_MTIME == mtime
    ):
        return _MODEL_CACHE

    with open(path, "r", encoding="utf-8") as model_file:
        model = json.load(model_file)

    _MODEL_CACHE = model
    _MODEL_CACHE_PATH = path
    _MODEL_CACHE_MTIME = mtime
    return model


def predict_quality_score(features: dict, model_path: str | None = None) -> tuple[float | None, dict]:
    """
    Predict quality score (0-100) from timetable features.

    Returns (score_or_none, metadata). Caller should fallback to rule score if score is None.
    """

    model = _load_model(model_path=model_path)
    if not model:
        return None, {"model_source": "rule_fallback", "reason": "model_not_found"}

    vector = _feature_vector(features)
    means = model.get("feature_means", [0.0] * len(vector))
    stds = model.get("feature_stds", [1.0] * len(vector))
    weights = model.get("weights", [0.0] * len(vector))
    bias = float(model.get("bias", 0.0))

    standardized = []
    for idx, value in enumerate(vector):
        mean = float(means[idx]) if idx < len(means) else 0.0
        std = float(stds[idx]) if idx < len(stds) else 1.0
        standardized.extend(_standardize([value], mean, std))

    z_value = bias
    for idx, value in enumerate(standardized):
        weight = float(weights[idx]) if idx < len(weights) else 0.0
        z_value += weight * value

    acceptance_prob = _sigmoid(z_value)
    score = round(acceptance_prob * 100.0, 2)
    return score, {
        "model_source": "learned_predictor",
        "acceptance_probability": round(acceptance_prob, 6),
    }


def train_quality_model_from_database(
    *,
    model_path: str | None = None,
    min_samples: int = 30,
    logger=None,
) -> dict:
    """
    Train a lightweight logistic model from accepted/rejected candidates.

    Labels are sourced from timetable_quality_candidates:
    - is_selected = 1  => accepted
    - is_selected = 0  => rejected
    """

    selected_model_path = os.path.abspath(model_path or _default_model_path())

    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                clash_risk,
                faculty_fatigue,
                room_overuse,
                student_load_imbalance,
                is_selected
            FROM timetable_quality_candidates
            WHERE clash_risk IS NOT NULL
              AND faculty_fatigue IS NOT NULL
              AND room_overuse IS NOT NULL
              AND student_load_imbalance IS NOT NULL
            """
        )
        rows = cursor.fetchall() or []
    except Exception as exc:
        if logger:
            logger.warning("Quality model training skipped: %s", str(exc))
        return {"status": "skipped", "reason": "query_failed", "error": str(exc)}
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()

    if len(rows) < max(2, int(min_samples)):
        return {
            "status": "skipped",
            "reason": "insufficient_samples",
            "sample_count": len(rows),
            "required_samples": int(min_samples),
        }

    raw_features: list[list[float]] = []
    labels: list[float] = []
    for row in rows:
        raw_features.append(
            [
                _clamp01(row.get("clash_risk", 1.0)),
                _clamp01(row.get("faculty_fatigue", 1.0)),
                _clamp01(row.get("room_overuse", 1.0)),
                _clamp01(row.get("student_load_imbalance", 1.0)),
            ]
        )
        labels.append(1.0 if int(row.get("is_selected", 0) or 0) == 1 else 0.0)

    feature_count = len(_FEATURE_NAMES)
    means = []
    stds = []
    standardized_features: list[list[float]] = []

    for col_index in range(feature_count):
        column = [row[col_index] for row in raw_features]
        mean = sum(column) / len(column)
        variance = sum((value - mean) ** 2 for value in column) / max(1, len(column))
        std = math.sqrt(max(variance, 1e-12))
        means.append(mean)
        stds.append(std)

    for row in raw_features:
        standardized_row = []
        for col_index, value in enumerate(row):
            denom = stds[col_index] if stds[col_index] > 1e-9 else 1.0
            standardized_row.append((value - means[col_index]) / denom)
        standardized_features.append(standardized_row)

    # Batch gradient descent for deterministic and dependency-free training.
    weights = [0.0] * feature_count
    bias = 0.0
    learning_rate = 0.12
    epochs = 450
    l2_lambda = 0.0005
    n = float(len(standardized_features))

    for _ in range(epochs):
        grad_w = [0.0] * feature_count
        grad_b = 0.0

        for idx, row in enumerate(standardized_features):
            y_true = labels[idx]
            z = bias
            for feature_idx, value in enumerate(row):
                z += weights[feature_idx] * value
            y_pred = _sigmoid(z)
            error = y_pred - y_true

            for feature_idx, value in enumerate(row):
                grad_w[feature_idx] += error * value
            grad_b += error

        for feature_idx in range(feature_count):
            grad_w[feature_idx] = (grad_w[feature_idx] / n) + (l2_lambda * weights[feature_idx])
            weights[feature_idx] -= learning_rate * grad_w[feature_idx]
        bias -= learning_rate * (grad_b / n)

    # Quick in-sample diagnostics for logs.
    correct = 0
    for idx, row in enumerate(standardized_features):
        z = bias
        for feature_idx, value in enumerate(row):
            z += weights[feature_idx] * value
        predicted_label = 1.0 if _sigmoid(z) >= 0.5 else 0.0
        if predicted_label == labels[idx]:
            correct += 1

    model_payload = {
        "model_type": "logistic_regression",
        "feature_names": _FEATURE_NAMES,
        "feature_means": means,
        "feature_stds": stds,
        "weights": weights,
        "bias": bias,
        "sample_count": len(rows),
        "training_accuracy": round(correct / len(rows), 6),
    }

    os.makedirs(os.path.dirname(selected_model_path), exist_ok=True)
    with open(selected_model_path, "w", encoding="utf-8") as model_file:
        json.dump(model_payload, model_file, ensure_ascii=True, indent=2)

    # Bust cache after a successful write.
    global _MODEL_CACHE, _MODEL_CACHE_PATH, _MODEL_CACHE_MTIME
    _MODEL_CACHE = None
    _MODEL_CACHE_PATH = None
    _MODEL_CACHE_MTIME = None

    if logger:
        logger.info(
            "Quality model trained with %d samples (acc=%.3f)",
            len(rows),
            model_payload["training_accuracy"],
        )

    return {
        "status": "trained",
        "sample_count": len(rows),
        "training_accuracy": model_payload["training_accuracy"],
        "model_path": selected_model_path,
    }
