from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Dict, List
from uuid import uuid4

from fuzzy.fuzzy_controller import FuzzyTrafficController
from simulation_db import SimulationDatabase


DB = SimulationDatabase()


@dataclass
class TrafficState:
    queue: Dict[str, float]
    total_wait: Dict[str, float]
    served: Dict[str, float]
    max_queue: float


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def _base_rates_from_weighted(weighted_by_dir: Dict[str, float]) -> Dict[str, float]:
    rates = {}
    for direction, weight in weighted_by_dir.items():
        rates[direction] = max(0.08, min(1.6, (weight / 260.0) + 0.15))
    return rates


def _build_phase_plan(intersection_type: str) -> List[Dict]:
    if intersection_type == "Perempatan":
        return [
            {
                "name": "Fase Bawah Lurus + Kiri->Bawah",
                "green_dirs": ["Selatan", "Barat"],
                "notes": "Saat bawah hijau, arus lurus kanan-kiri ditahan merah.",
            },
            {
                "name": "Fase Utara + Selatan",
                "green_dirs": ["Utara", "Selatan"],
                "notes": "Arus vertikal prioritas.",
            },
            {
                "name": "Fase Timur + Barat",
                "green_dirs": ["Timur", "Barat"],
                "notes": "Arus horizontal prioritas.",
            },
        ]
    return [
        {
            "name": "Fase Utara+Timur",
            "green_dirs": ["Utara", "Timur"],
            "notes": "Skenario pertigaan set 1.",
        },
        {
            "name": "Fase Utara+Barat",
            "green_dirs": ["Utara", "Barat"],
            "notes": "Skenario pertigaan set 2.",
        },
    ]


def _phase_pressure(phase: Dict, weighted_by_dir: Dict[str, float], queue: Dict[str, float]) -> float:
    active_dirs = phase["green_dirs"]
    base_load = sum(weighted_by_dir[d] for d in active_dirs)
    queued = sum(queue[d] for d in active_dirs)
    return base_load + queued * 1.5


def _green_duration(
    *,
    mode: str,
    phase: Dict,
    weighted_by_dir: Dict[str, float],
    queue: Dict[str, float],
    min_green: int,
    max_green: int,
    fuzzy: FuzzyTrafficController,
) -> int:
    if mode == "fixed":
        return int(_clamp(30, min_green, max_green))
    pressure = _phase_pressure(phase, weighted_by_dir, queue)
    fuzzy_input = int(_clamp(round(pressure / 5.0), 0, 30))
    inferred, _detail = fuzzy.infer(fuzzy_input)
    return int(_clamp(inferred, min_green, max_green))


def _build_direction_stats(
    directions: List[str],
    green_samples_by_dir: Dict[str, List[int]],
    red_samples_by_dir: Dict[str, List[int]],
) -> List[Dict]:
    rows: List[Dict] = []
    for direction in directions:
        green_samples = green_samples_by_dir.get(direction, [])
        red_samples = red_samples_by_dir.get(direction, [])
        total_green = float(sum(green_samples))
        total_red = float(sum(red_samples))
        rows.append({
            "direction": direction,
            "green_count": len(green_samples),
            "total_green_s": total_green,
            "avg_green_s": round(total_green / max(len(green_samples), 1), 3),
            "max_green_s": float(max(green_samples)) if green_samples else 0.0,
            "total_red_s": total_red,
            "avg_red_s": round(total_red / max(len(red_samples), 1), 3),
            "max_red_s": float(max(red_samples)) if red_samples else 0.0,
        })
    return rows


def _simulate_one_controller(
    *,
    intersection_type: str,
    weighted_by_dir: Dict[str, float],
    controller_mode: str,
    duration_steps: int = 1800,
    min_green: int = 10,
    max_green: int = 60,
    yellow: int = 3,
    all_red: int = 1,
    service_rate_green: float = 1.8,
    service_rate_red: float = 0.15,
    comparison_group_id: str | None = None,
) -> Dict:
    phase_plan = _build_phase_plan(intersection_type)
    arrival_rates = _base_rates_from_weighted(weighted_by_dir)
    directions = list(weighted_by_dir.keys())
    fuzzy = FuzzyTrafficController()

    state = TrafficState(
        queue={d: 0.0 for d in directions},
        total_wait={d: 0.0 for d in directions},
        served={d: 0.0 for d in directions},
        max_queue=0.0,
    )

    phase_idx = 0
    next_phase_idx = 1 % len(phase_plan)
    current_phase = phase_plan[phase_idx]
    current_green = _green_duration(
        mode=controller_mode,
        phase=current_phase,
        weighted_by_dir=weighted_by_dir,
        queue=state.queue,
        min_green=min_green,
        max_green=max_green,
        fuzzy=fuzzy,
    )
    state_mode = "GREEN"
    countdown = current_green
    timeline = []
    red_streak_by_dir = {d: 0 for d in directions}
    red_samples_by_dir = {d: [] for d in directions}
    green_streak_by_dir = {d: 0 for d in directions}
    green_samples_by_dir = {d: [] for d in directions}
    run_started_at = datetime.now(timezone.utc)
    telemetry = DB.create_run({
        "comparison_group_id": comparison_group_id,
        "engine": "internal_python",
        "controller_mode": controller_mode,
        "intersection_type": intersection_type,
        "sumo_cfg": None,
        "tl_id": None,
        "resolved_tl_id": None,
        "use_gui": False,
        "custom_fourway_logic": None,
        "duration_steps": duration_steps,
        "min_green": min_green,
        "max_green": max_green,
        "yellow": yellow,
        "all_red": all_red,
        "weighted_by_dir": weighted_by_dir,
        "phase_plan": phase_plan,
        "started_at": run_started_at,
    })
    phase_started_at = 0
    telemetry.record_phase_event(
        step_index=0,
        event_type="green_start",
        phase_name=current_phase["name"],
        phase_index=phase_idx,
        stage="GREEN",
        assigned_duration=current_green,
        actual_duration=None,
        reason="initial",
        directions=current_phase["green_dirs"],
    )

    try:
        for step in range(duration_steps):
            if state_mode == "GREEN":
                active_green_dirs = current_phase["green_dirs"]
            else:
                active_green_dirs = []

            for direction in directions:
                is_green = state_mode == "GREEN" and direction in active_green_dirs
                if is_green:
                    green_streak_by_dir[direction] += 1
                    if red_streak_by_dir[direction] > 0:
                        red_samples_by_dir[direction].append(red_streak_by_dir[direction])
                        red_streak_by_dir[direction] = 0
                else:
                    if green_streak_by_dir[direction] > 0:
                        green_samples_by_dir[direction].append(green_streak_by_dir[direction])
                        green_streak_by_dir[direction] = 0
                    red_streak_by_dir[direction] += 1

            total_queue_now = 0.0
            for direction in directions:
                direction_seed = (sum(ord(ch) for ch in direction) % 9) / 10.0
                wave = 1.0 + 0.18 * math.sin((step / 45.0) + direction_seed)
                arrivals = arrival_rates[direction] * wave

                if direction in active_green_dirs:
                    service = service_rate_green * (0.85 + 0.25 * (state.queue[direction] > 2.0))
                elif state_mode == "YELLOW":
                    service = 0.03
                elif state_mode == "ALL_RED":
                    service = 0.0
                else:
                    service = service_rate_red

                next_q = max(0.0, state.queue[direction] + arrivals - service)
                departed = max(0.0, state.queue[direction] + arrivals - next_q)
                state.queue[direction] = next_q
                state.served[direction] += departed
                state.total_wait[direction] += next_q
                total_queue_now += next_q

            state.max_queue = max(state.max_queue, total_queue_now)
            timeline.append(
                {
                    "step": step,
                    "queue_total": total_queue_now,
                    "phase": current_phase["name"],
                    "status": state_mode,
                    "green_time": current_green,
                    "phase_index": phase_idx,
                }
            )
            phase_queue = sum(state.queue[d] for d in current_phase["green_dirs"])
            telemetry.record_step(
                step_index=step,
                phase_name=current_phase["name"],
                phase_index=phase_idx,
                status=state_mode,
                green_time=current_green,
                queue_total=total_queue_now,
                avg_wait_s=total_queue_now / max(sum(state.served.values()), 1.0),
                phase_queue=phase_queue,
                phase_score=_phase_pressure(current_phase, weighted_by_dir, state.queue),
                direction_state={
                    direction: {
                        "is_green": direction in active_green_dirs,
                        "queue_count": state.queue[direction],
                        "red_age": red_streak_by_dir[direction],
                        "red_streak": red_streak_by_dir[direction],
                        "pressure": state.queue[direction] + weighted_by_dir[direction],
                    }
                    for direction in directions
                },
            )

            if state_mode == "GREEN":
                countdown -= 1
                if countdown <= 0:
                    telemetry.record_phase_event(
                        step_index=step,
                        event_type="yellow_start",
                        phase_name=current_phase["name"],
                        phase_index=phase_idx,
                        stage="YELLOW",
                        assigned_duration=int(yellow),
                        actual_duration=step - phase_started_at + 1,
                        reason="green_elapsed",
                        directions=current_phase["green_dirs"],
                    )
                    state_mode = "YELLOW"
                    phase_started_at = step + 1
                    countdown = max(1, int(yellow))
            elif state_mode == "YELLOW":
                countdown -= 1
                if countdown <= 0:
                    telemetry.record_phase_event(
                        step_index=step,
                        event_type="all_red_start",
                        phase_name=current_phase["name"],
                        phase_index=phase_idx,
                        stage="ALL_RED",
                        assigned_duration=int(all_red),
                        actual_duration=step - phase_started_at + 1,
                        reason="yellow_elapsed",
                        directions=current_phase["green_dirs"],
                    )
                    state_mode = "ALL_RED"
                    phase_started_at = step + 1
                    countdown = max(0, int(all_red))
            else:
                countdown -= 1
                if countdown <= 0:
                    phase_idx = next_phase_idx
                    next_phase_idx = (phase_idx + 1) % len(phase_plan)
                    current_phase = phase_plan[phase_idx]
                    current_green = _green_duration(
                        mode=controller_mode,
                        phase=current_phase,
                        weighted_by_dir=weighted_by_dir,
                        queue=state.queue,
                        min_green=min_green,
                        max_green=max_green,
                        fuzzy=fuzzy,
                    )
                    state_mode = "GREEN"
                    phase_started_at = step + 1
                    countdown = current_green
                    telemetry.record_phase_event(
                        step_index=step,
                        event_type="green_start",
                        phase_name=current_phase["name"],
                        phase_index=phase_idx,
                        stage="GREEN",
                        assigned_duration=current_green,
                        actual_duration=None,
                        reason="phase_rotation",
                        directions=current_phase["green_dirs"],
                    )
    except Exception as exc:
        telemetry.complete({}, error_message=str(exc))
        DB.persist(telemetry)
        raise

    for direction in directions:
        if green_streak_by_dir[direction] > 0:
            green_samples_by_dir[direction].append(green_streak_by_dir[direction])
        if red_streak_by_dir[direction] > 0:
            red_samples_by_dir[direction].append(red_streak_by_dir[direction])

    total_served = sum(state.served.values())
    avg_wait = sum(state.total_wait.values()) / max(total_served, 1.0)
    avg_queue = sum(row["queue_total"] for row in timeline) / max(len(timeline), 1)
    throughput_per_min = total_served / max(duration_steps / 60.0, 1e-6)
    density_index = avg_queue / max(1.0, len(directions) * 20.0)

    waits = [state.total_wait[d] / max(state.served[d], 1.0) for d in directions]
    fairness = max(waits) - min(waits) if waits else 0.0
    all_red_samples = [sample for samples in red_samples_by_dir.values() for sample in samples]
    avg_red = sum(all_red_samples) / max(len(all_red_samples), 1)
    max_red = max(all_red_samples) if all_red_samples else 0.0

    result = {
        "kpi": {
            "avg_wait_s": round(avg_wait, 3),
            "avg_red_s": round(avg_red, 3),
            "max_red_s": round(max_red, 3),
            "max_queue": round(state.max_queue, 3),
            "avg_queue": round(avg_queue, 3),
            "throughput_per_min": round(throughput_per_min, 3),
            "density_index": round(density_index, 3),
            "phase_fairness_gap": round(fairness, 3),
            "total_served": round(total_served, 3),
        },
        "timeline": timeline,
        "phase_plan": phase_plan,
    }

    direction_stats = _build_direction_stats(directions, green_samples_by_dir, red_samples_by_dir)
    telemetry.set_direction_stats(direction_stats)
    telemetry.complete(result["kpi"])
    DB.persist(telemetry)
    return result


def run_comparison(
    *,
    intersection_type: str,
    weighted_by_dir: Dict[str, float],
    duration_steps: int = 1800,
    min_green: int = 10,
    max_green: int = 60,
    yellow: int = 3,
    all_red: int = 1,
) -> Dict:
    comparison_group_id = str(uuid4())
    fixed = _simulate_one_controller(
        intersection_type=intersection_type,
        weighted_by_dir=weighted_by_dir,
        controller_mode="fixed",
        duration_steps=duration_steps,
        min_green=min_green,
        max_green=max_green,
        yellow=yellow,
        all_red=all_red,
        comparison_group_id=comparison_group_id,
    )
    fuzzy = _simulate_one_controller(
        intersection_type=intersection_type,
        weighted_by_dir=weighted_by_dir,
        controller_mode="fuzzy",
        duration_steps=duration_steps,
        min_green=min_green,
        max_green=max_green,
        yellow=yellow,
        all_red=all_red,
        comparison_group_id=comparison_group_id,
    )
    return {"fixed": fixed, "fuzzy": fuzzy}
