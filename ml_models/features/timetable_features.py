from __future__ import annotations

from collections import defaultdict
from statistics import mean


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def extract_timetable_features(
    assigned: list[dict],
    unassigned: list[dict],
    proxy_suggestions: list[dict],
    needs_room: list[dict],
    slots_per_day: dict[str, int] | None = None,
) -> dict:
    """Compute normalized quality risk dimensions from timetable generation output."""

    assigned = assigned or []
    unassigned = unassigned or []
    proxy_suggestions = proxy_suggestions or []
    needs_room = needs_room or []
    slots_per_day = slots_per_day or {}

    total_slots = max(1, len(assigned) + len(unassigned))
    total_days = max(1, len(slots_per_day))

    # 1) Clash risk: unresolved sessions and room-missing sessions relative to total slots.
    unassigned_count = len(unassigned)
    needs_room_count = len(needs_room)
    unresolved = unassigned_count + needs_room_count
    clash_risk = _clamp01(unresolved / total_slots)

    # 2) Faculty fatigue: penalize long consecutive runs and overloaded day counts per faculty.
    faculty_day_sessions: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for entry in assigned:
        faculty_id = entry.get("faculty_id")
        day = entry.get("day")
        if faculty_id is None or not day:
            continue
        faculty_day_sessions[(int(faculty_id), day)].append(entry)

    fatigue_penalty = 0.0
    fatigue_denominator = max(1, len(faculty_day_sessions))
    for key in faculty_day_sessions:
        sessions = faculty_day_sessions[key]
        sessions.sort(key=lambda s: s.get("start_time", ""))
        day_count = len(sessions)

        # Mild penalty after 4 sessions/day, steeper after 6.
        fatigue_penalty += max(0, day_count - 4) * 0.08
        fatigue_penalty += max(0, day_count - 6) * 0.05

        # Penalty for 3+ consecutive same-day slots.
        run_length = 1
        for idx in range(1, len(sessions)):
            prev_end = sessions[idx - 1].get("end_time")
            this_start = sessions[idx].get("start_time")
            if prev_end == this_start:
                run_length += 1
                if run_length >= 3:
                    fatigue_penalty += 0.1
            else:
                run_length = 1

    faculty_fatigue = _clamp01(fatigue_penalty / fatigue_denominator)

    # 3) Room overuse: pressure from missing room assignments and concentrated room usage.
    room_counts: dict[int, int] = defaultdict(int)
    for entry in assigned:
        room_id = entry.get("room_id")
        if room_id:
            room_counts[int(room_id)] += 1

    room_pressure = (len(needs_room) / total_slots)
    concentration_penalty = 0.0
    max_room_share = 0.0
    if room_counts:
        max_room_share = max(room_counts.values()) / max(1, sum(room_counts.values()))
        # Start penalizing when one room carries >35% of all assignments.
        concentration_penalty = max(0.0, max_room_share - 0.35)

    room_overuse = _clamp01(room_pressure + concentration_penalty)

    # 4) Student load imbalance: uneven day-wise spread for assigned sessions.
    assigned_per_day: dict[str, int] = defaultdict(int)
    for entry in assigned:
        day = entry.get("day")
        if day:
            assigned_per_day[day] += 1

    # Include all selected working days even if no sessions assigned there.
    all_days = list(slots_per_day.keys()) if slots_per_day else list(assigned_per_day.keys())
    if not all_days:
        all_days = ["Monday"]
    loads = [assigned_per_day.get(day, 0) for day in all_days]
    avg_load = max(1e-6, mean(loads))
    max_dev = max(abs(value - avg_load) for value in loads) if loads else 0.0
    student_load_imbalance = _clamp01(max_dev / avg_load)

    # Useful supportive metrics for warnings and candidate summary.
    proxy_ratio = _clamp01(len(proxy_suggestions) / total_slots)
    day_density = {
        day: {
            "assigned": assigned_per_day.get(day, 0),
            "capacity": int(slots_per_day.get(day, 0)),
        }
        for day in all_days
    }

    return {
        "clash_risk": clash_risk,
        "faculty_fatigue": faculty_fatigue,
        "room_overuse": room_overuse,
        "student_load_imbalance": student_load_imbalance,
        "proxy_ratio": proxy_ratio,
        "day_density": day_density,
        "total_slots": total_slots,
        "total_days": total_days,
        "unassigned_count": unassigned_count,
        "needs_room_count": needs_room_count,
        "max_room_share": _clamp01(max_room_share),
    }
