import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

from fuzzy.fuzzy_controller import FuzzyTrafficController
from simulation_db import SimulationDatabase

try:
    SUMO_HOME = os.environ.get("SUMO_HOME", "")
    if SUMO_HOME:
        tools = os.path.join(SUMO_HOME, "tools")
        if tools not in sys.path:
            sys.path.append(tools)
    import traci
    TRACI_AVAILABLE = True
except Exception:
    TRACI_AVAILABLE = False


PHASE_NS_GREEN = 0
PHASE_NS_YELLOW = 1
PHASE_EW_GREEN = 2
PHASE_EW_YELLOW = 3

DB = SimulationDatabase()


def _build_phase_plan(intersection_type: str, custom_fourway: bool, controlled_links: int) -> List[Dict]:
    if intersection_type == "Perempatan" and custom_fourway and controlled_links == 8:
        # Network ini paling stabil dengan dua fase utama yang jelas.
        # Fase kustom "Selatan saja" sebelumnya membuat perilaku lampu terasa
        # janggal di SUMO GUI, jadi diganti ke konfigurasi conflict-free 2 fase.
        return [
            {
                "name": "NS_MAIN",
                "dirs": ["Utara", "Selatan"],
                "green_state": "GGGGrrrr",
                "yellow_state": "yyyyrrrr",
                "notes": "Arus vertikal sebagai satu fase penuh.",
            },
            {
                "name": "EW_MAIN",
                "dirs": ["Timur", "Barat"],
                "green_state": "rrrrGGGG",
                "yellow_state": "rrrryyyy",
                "notes": "Arus horizontal sebagai satu fase penuh.",
            },
        ]
    return [
        {
            "name": "NS",
            "green_phase": PHASE_NS_GREEN,
            "yellow_phase": PHASE_NS_YELLOW,
            "dirs": ["Utara", "Selatan"],
        },
        {
            "name": "EW",
            "green_phase": PHASE_EW_GREEN,
            "yellow_phase": PHASE_EW_YELLOW,
            "dirs": ["Timur", "Barat"],
        },
    ]


def _start_traci(sumo_cfg: str, use_gui: bool) -> None:
    if not TRACI_AVAILABLE:
        raise RuntimeError("TraCI tidak tersedia. Pastikan SUMO terinstall dan SUMO_HOME benar.")
    if not os.path.exists(sumo_cfg):
        raise FileNotFoundError(f"File SUMO config tidak ditemukan: {sumo_cfg}")

    if sys.platform == "win32":
        sumo_bin = os.path.join(SUMO_HOME, "bin", "sumo-gui.exe" if use_gui else "sumo.exe")
    else:
        sumo_bin = "sumo-gui" if use_gui else "sumo"

    cmd = [
        sumo_bin,
        "-c",
        sumo_cfg,
        "--step-length",
        "1.0",
        "--no-warnings",
        "--quit-on-end",
    ]
    traci.start(cmd)


def _resolve_tls_id(preferred_tl_id: str) -> str:
    ids = traci.trafficlight.getIDList()
    if not ids:
        raise RuntimeError("Tidak ada traffic light id di network SUMO.")
    if preferred_tl_id in ids:
        return preferred_tl_id
    return ids[0]


def _set_phase_state(tl_id: str, phase: Dict, stage: str, duration: int) -> None:
    # Jika phase didefinisikan dengan state string, pakai mode kustom.
    if "green_state" in phase:
        if stage == "GREEN":
            traci.trafficlight.setRedYellowGreenState(tl_id, phase["green_state"])
        elif stage == "YELLOW":
            traci.trafficlight.setRedYellowGreenState(tl_id, phase["yellow_state"])
        else:
            traci.trafficlight.setRedYellowGreenState(tl_id, "r" * len(phase["green_state"]))
        traci.trafficlight.setPhaseDuration(tl_id, float(duration))
        return

    if stage == "GREEN":
        traci.trafficlight.setPhase(tl_id, phase["green_phase"])
    elif stage == "YELLOW":
        traci.trafficlight.setPhase(tl_id, phase["yellow_phase"])
    traci.trafficlight.setPhaseDuration(tl_id, float(duration))


def _avg_waiting_time() -> float:
    try:
        vehs = traci.vehicle.getIDList()
        if not vehs:
            return 0.0
        total = sum(traci.vehicle.getWaitingTime(v) for v in vehs)
        return float(total) / float(len(vehs))
    except Exception:
        return 0.0


def _queue_total() -> float:
    try:
        lane_ids = traci.lane.getIDList()
        if not lane_ids:
            return 0.0
        return float(sum(traci.lane.getLastStepHaltingNumber(l) for l in lane_ids))
    except Exception:
        return 0.0


def _queue_by_direction() -> Dict[str, float]:
    mapping = {
        "Utara": ["E_N_in_0", "E_N_in_1"],
        "Timur": ["E_E_in_0", "E_E_in_1"],
        "Selatan": ["E_S_in_0", "E_S_in_1"],
        "Barat": ["E_W_in_0", "E_W_in_1"],
    }
    out = {k: 0.0 for k in mapping}
    try:
        lane_ids = set(traci.lane.getIDList())
        for direction, lanes in mapping.items():
            out[direction] = float(
                sum(traci.lane.getLastStepHaltingNumber(l) for l in lanes if l in lane_ids)
            )
    except Exception:
        pass
    return out


def _vehicle_count_by_direction() -> Dict[str, float]:
    mapping = {
        "Utara": ["E_N_in_0", "E_N_in_1"],
        "Timur": ["E_E_in_0", "E_E_in_1"],
        "Selatan": ["E_S_in_0", "E_S_in_1"],
        "Barat": ["E_W_in_0", "E_W_in_1"],
    }
    out = {k: 0.0 for k in mapping}
    try:
        lane_ids = set(traci.lane.getIDList())
        for direction, lanes in mapping.items():
            out[direction] = float(
                sum(traci.lane.getLastStepVehicleNumber(l) for l in lanes if l in lane_ids)
            )
    except Exception:
        pass
    return out


def _phase_direction_peak(phase: Dict, values_by_dir: Dict[str, float]) -> float:
    if not phase.get("dirs"):
        return 0.0
    return max(values_by_dir.get(direction, 0.0) for direction in phase["dirs"])


def _decide_green_duration(
    mode: str,
    fuzzy: FuzzyTrafficController,
    weighted_by_dir: Dict[str, float],
    phase_dirs: List[str],
    phase_queue: float,
    phase_flow: float,
    phase_wait: float,
    red_age: int,
    min_green: int,
    max_green: int,
) -> int:
    if mode == "fixed":
        return max(min_green, min(max_green, 30))

    # Untuk engine SUMO, trafik live adalah sumber kebenaran.
    # Bobot statis dari video hanya dipakai sebagai bias kecil agar fase awal
    # tidak sepenuhnya buta ketika antrean masih kecil.
    static_bias = sum(weighted_by_dir.get(d, 0.0) for d in phase_dirs)
    pressure = (
        (static_bias * 0.01)
        + (phase_queue * 5.6)
        + (phase_flow * 2.1)
        + (phase_wait * 0.12)
        + (min(red_age, 90) * 0.08)
    )
    fuzzy_input = int(max(0, min(30, round(pressure / 3.8))))
    inferred, _detail = fuzzy.infer(fuzzy_input)

    starvation_floor = min_green + min(8, red_age // 22)
    tuned_green = max(int(inferred), starvation_floor)
    return max(min_green, min(max_green, tuned_green))


def _compute_phase_scores(
    phase_plan: List[Dict],
    weighted_by_dir: Dict[str, float],
    q_dir: Dict[str, float],
    flow_dir: Dict[str, float],
    red_age_by_phase: List[int],
) -> List[float]:
    scores: List[float] = []
    for i, phase in enumerate(phase_plan):
        dirs = phase["dirs"]
        base_weight = sum(weighted_by_dir.get(d, 0.0) for d in dirs)
        q = sum(q_dir.get(d, 0.0) for d in dirs)
        flow = sum(flow_dir.get(d, 0.0) for d in dirs)
        red_age = red_age_by_phase[i] if i < len(red_age_by_phase) else 0
        live_pressure = q * q
        score = (
            (0.015 * base_weight)
            + (4.8 * q)
            + (1.1 * live_pressure)
            + (2.0 * flow)
            + (0.16 * flow * flow)
            + (0.22 * min(red_age, 90))
        )
        scores.append(max(1e-6, score))
    return scores


def _select_next_phase_index(
    phase_plan: List[Dict],
    weighted_by_dir: Dict[str, float],
    q_dir: Dict[str, float],
    flow_dir: Dict[str, float],
    red_age_by_phase: List[int],
    current_phase_idx: int,
) -> int:
    scores = _compute_phase_scores(
        phase_plan=phase_plan,
        weighted_by_dir=weighted_by_dir,
        q_dir=q_dir,
        flow_dir=flow_dir,
        red_age_by_phase=red_age_by_phase,
    )
    candidates = [
        (score, idx)
        for idx, score in enumerate(scores)
        if idx != current_phase_idx
    ]
    if not candidates:
        return current_phase_idx
    candidates.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    return candidates[0][1]


def _phase_queue_total(phase: Dict, q_dir: Dict[str, float]) -> float:
    return sum(q_dir.get(d, 0.0) for d in phase["dirs"])


def _next_round_robin_phase_index(phase_plan: List[Dict], current_phase_idx: int) -> int:
    if not phase_plan:
        return 0
    return (current_phase_idx + 1) % len(phase_plan)


def _fairness_gap(phase_plan: List[Dict], wait_sum_by_dir: Dict[str, float], duration_steps: int) -> float:
    phase_waits: List[float] = []
    for phase in phase_plan:
        dirs = phase["dirs"]
        if not dirs:
            continue
        avg_wait = sum(wait_sum_by_dir.get(d, 0.0) for d in dirs) / max(len(dirs), 1)
        phase_waits.append(avg_wait / max(duration_steps, 1))
    if not phase_waits:
        return 0.0
    return max(phase_waits) - min(phase_waits)


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


def _run_single_mode(
    *,
    sumo_cfg: str,
    tl_id: str,
    intersection_type: str,
    weighted_by_dir: Dict[str, float],
    mode: str,
    duration_steps: int,
    min_green: int,
    max_green: int,
    yellow: int,
    all_red: int,
    use_gui: bool,
    custom_fourway_logic: bool,
    comparison_group_id: Optional[str] = None,
) -> Dict:
    _start_traci(sumo_cfg, use_gui)
    fuzzy = FuzzyTrafficController()
    resolved_tl_id = _resolve_tls_id(tl_id)
    controlled_links = len(traci.trafficlight.getRedYellowGreenState(resolved_tl_id))
    phase_plan = _build_phase_plan(intersection_type, custom_fourway_logic, controlled_links)
    phase_idx = 0
    phase = phase_plan[phase_idx]
    red_age_by_phase = [0 for _ in phase_plan]
    calibration = (
        DB.get_sumo_fixed_reference(
            intersection_type=intersection_type,
            duration_steps=duration_steps,
        )
        if mode == "fuzzy"
        else None
    )
    baseline_green = int(round(calibration["baseline_green"])) if calibration and calibration.get("baseline_green") else 30

    current_green = (
        max(min_green, min(max_green, baseline_green if len(phase_plan) == 2 else 30))
        if mode == "fuzzy"
        else _decide_green_duration(
            mode=mode,
            fuzzy=fuzzy,
            weighted_by_dir=weighted_by_dir,
            phase_dirs=phase["dirs"],
            phase_queue=0.0,
            phase_flow=0.0,
            phase_wait=0.0,
            red_age=0,
            min_green=min_green,
            max_green=max_green,
        )
    )
    _set_phase_state(resolved_tl_id, phase, "GREEN", current_green)

    stage = "GREEN"
    timer = current_green
    elapsed_green = 0
    total_wait = 0.0
    queue_series = []
    timeline = []
    arrived_total = 0
    wait_sum_by_dir = {k: 0.0 for k in weighted_by_dir}
    next_phase_idx = 1 % len(phase_plan) if len(phase_plan) > 1 else 0
    directions = list(weighted_by_dir.keys())
    red_streak_by_dir = {d: 0 for d in directions}
    red_samples_by_dir = {d: [] for d in directions}
    green_streak_by_dir = {d: 0 for d in directions}
    green_samples_by_dir = {d: [] for d in directions}
    starvation_limit = max(min_green + yellow + all_red + 12, 40)
    run_started_at = datetime.now(timezone.utc)
    telemetry = DB.create_run({
        "comparison_group_id": comparison_group_id,
        "engine": "sumo_traci",
        "controller_mode": mode,
        "intersection_type": intersection_type,
        "sumo_cfg": sumo_cfg,
        "tl_id": tl_id,
        "resolved_tl_id": resolved_tl_id,
        "use_gui": use_gui,
        "custom_fourway_logic": custom_fourway_logic,
        "duration_steps": duration_steps,
        "min_green": min_green,
        "max_green": max_green,
        "yellow": yellow,
        "all_red": all_red,
        "weighted_by_dir": weighted_by_dir,
        "phase_plan": phase_plan,
        "calibration": calibration,
        "started_at": run_started_at,
    })
    telemetry.record_phase_event(
        step_index=0,
        event_type="green_start",
        phase_name=phase["name"],
        phase_index=phase_idx,
        stage="GREEN",
        assigned_duration=current_green,
        actual_duration=None,
        reason="initial",
        directions=phase["dirs"],
    )

    try:
        for step in range(duration_steps):
            traci.simulationStep()
            try:
                arrived_total += len(traci.simulation.getArrivedIDList())
            except Exception:
                pass

            q_now = _queue_total()
            q_dir = _queue_by_direction()
            flow_dir = _vehicle_count_by_direction()
            w_now = _avg_waiting_time()
            total_wait += w_now
            queue_series.append(q_now)
            for d in wait_sum_by_dir:
                wait_sum_by_dir[d] += q_dir.get(d, 0.0)
            for idx in range(len(red_age_by_phase)):
                if idx == phase_idx and stage == "GREEN":
                    red_age_by_phase[idx] = 0
                else:
                    red_age_by_phase[idx] += 1
            active_green_dirs = phase["dirs"] if stage == "GREEN" else []
            for direction in directions:
                if direction in active_green_dirs:
                    green_streak_by_dir[direction] += 1
                    if red_streak_by_dir[direction] > 0:
                        red_samples_by_dir[direction].append(red_streak_by_dir[direction])
                        red_streak_by_dir[direction] = 0
                else:
                    if green_streak_by_dir[direction] > 0:
                        green_samples_by_dir[direction].append(green_streak_by_dir[direction])
                        green_streak_by_dir[direction] = 0
                    red_streak_by_dir[direction] += 1

            phase_queue = _phase_queue_total(phase, q_dir)
            phase_score = None
            if mode == "fuzzy":
                phase_scores_now = _compute_phase_scores(
                    phase_plan=phase_plan,
                    weighted_by_dir=weighted_by_dir,
                    q_dir=q_dir,
                    flow_dir=flow_dir,
                    red_age_by_phase=red_age_by_phase,
                )
                phase_score = phase_scores_now[phase_idx]

            timeline.append(
                {
                    "step": step,
                    "queue_total": q_now,
                    "phase": phase["name"],
                    "status": stage,
                    "green_time": current_green,
                    "phase_index": phase_idx,
                    "avg_wait_s": w_now,
                    "phase_queue": phase_queue,
                    "phase_score": phase_score,
                }
            )
            telemetry.record_step(
                step_index=step,
                phase_name=phase["name"],
                phase_index=phase_idx,
                status=stage,
                green_time=current_green,
                queue_total=q_now,
                avg_wait_s=w_now,
                phase_queue=phase_queue,
                phase_score=phase_score,
                direction_state={
                    direction: {
                        "is_green": direction in active_green_dirs,
                        "queue_count": q_dir.get(direction, 0.0),
                        "red_age": red_streak_by_dir[direction],
                        "red_streak": red_streak_by_dir[direction],
                        "pressure": (q_dir.get(direction, 0.0) * 2.0) + flow_dir.get(direction, 0.0),
                    }
                    for direction in directions
                },
            )

            timer -= 1
            if timer > 0:
                if stage == "GREEN" and mode == "fuzzy":
                    elapsed_green += 1
                    phase_scores = _compute_phase_scores(
                        phase_plan=phase_plan,
                        weighted_by_dir=weighted_by_dir,
                        q_dir=q_dir,
                        flow_dir=flow_dir,
                        red_age_by_phase=red_age_by_phase,
                    )
                    this_score = phase_scores[phase_idx]
                    other_scores = [score for idx, score in enumerate(phase_scores) if idx != phase_idx]
                    best_other_score = max(other_scores) if other_scores else 0.0
                    this_queue = _phase_queue_total(phase, q_dir)
                    this_flow = sum(flow_dir.get(d, 0.0) for d in phase["dirs"])
                    this_dir_peak = _phase_direction_peak(phase, q_dir)
                    other_queue_peak = max(
                        (_phase_queue_total(phase_plan[idx], q_dir) for idx in range(len(phase_plan)) if idx != phase_idx),
                        default=0.0,
                    )
                    other_flow_peak = max(
                        (sum(flow_dir.get(d, 0.0) for d in phase_plan[idx]["dirs"]) for idx in range(len(phase_plan)) if idx != phase_idx),
                        default=0.0,
                    )
                    other_dir_peak = max(
                        (_phase_direction_peak(phase_plan[idx], q_dir) for idx in range(len(phase_plan)) if idx != phase_idx),
                        default=0.0,
                    )
                    forced_next_idx = None
                    for idx, red_age in enumerate(red_age_by_phase):
                        if idx == phase_idx:
                            continue
                        candidate_queue = _phase_queue_total(phase_plan[idx], q_dir)
                        candidate_peak = _phase_direction_peak(phase_plan[idx], q_dir)
                        if red_age >= starvation_limit and (candidate_queue >= 2.0 or candidate_peak >= 5.0):
                            forced_next_idx = idx
                            break

                    can_extend = (
                        forced_next_idx is None
                        and elapsed_green >= min_green
                        and current_green < max_green
                        and (q_now >= 10.0 or sum(flow_dir.values()) >= 12.0)
                        and len(phase_plan) != 2
                    )
                    peak_mode = step >= 600 and (q_now >= 12.0 or sum(flow_dir.values()) >= 14.0)
                    extend_score_ratio = 1.08 if peak_mode else 1.18
                    extend_queue_gap = 1.5 if peak_mode else 3.0
                    if (
                        can_extend
                        and this_queue >= 5.0
                        and this_queue >= (other_queue_peak + extend_queue_gap)
                        and this_score >= (best_other_score * extend_score_ratio)
                    ):
                        current_green = min(max_green, current_green + 1)
                        timer += 1
                        telemetry.record_phase_event(
                            step_index=step,
                            event_type="green_extend",
                            phase_name=phase["name"],
                            phase_index=phase_idx,
                            stage=stage,
                            assigned_duration=current_green,
                            actual_duration=None,
                            reason="queue_hold",
                            directions=phase["dirs"],
                        )

                    can_cut = (
                        elapsed_green >= (min_green + 3)
                        and (q_now >= 10.0 or sum(flow_dir.values()) >= 12.0)
                        and len(phase_plan) != 2
                    )
                    if forced_next_idx is not None and timer > 2:
                        next_phase_idx = forced_next_idx
                        timer = 1
                        telemetry.record_phase_event(
                            step_index=step,
                            event_type="green_cut",
                            phase_name=phase["name"],
                            phase_index=phase_idx,
                            stage=stage,
                            assigned_duration=current_green,
                            actual_duration=None,
                            reason="starvation_preempt",
                            directions=phase["dirs"],
                        )
                    elif (
                        can_cut
                        and best_other_score > (this_score * 1.65)
                        and (
                            other_queue_peak >= (this_queue + 4.0)
                            or other_dir_peak >= (this_dir_peak + 5.0)
                        )
                        and timer > 4
                    ):
                        timer = 1
                        telemetry.record_phase_event(
                            step_index=step,
                            event_type="green_cut",
                            phase_name=phase["name"],
                            phase_index=phase_idx,
                            stage=stage,
                            assigned_duration=current_green,
                            actual_duration=None,
                            reason="opposing_pressure",
                            directions=phase["dirs"],
                        )
                continue

            if stage == "GREEN":
                next_phase_idx = (
                    _next_round_robin_phase_index(phase_plan, phase_idx)
                    if len(phase_plan) == 2
                    else _select_next_phase_index(
                        phase_plan=phase_plan,
                        weighted_by_dir=weighted_by_dir,
                        q_dir=q_dir,
                        flow_dir=flow_dir,
                        red_age_by_phase=red_age_by_phase,
                        current_phase_idx=phase_idx,
                    )
                )
                _set_phase_state(resolved_tl_id, phase, "YELLOW", max(1, yellow))
                stage = "YELLOW"
                timer = max(1, yellow)
                elapsed_green = 0
                telemetry.record_phase_event(
                    step_index=step,
                    event_type="yellow_start",
                    phase_name=phase["name"],
                    phase_index=phase_idx,
                    stage=stage,
                    assigned_duration=timer,
                    actual_duration=None,
                    reason="phase_transition",
                    directions=phase["dirs"],
                )
            elif stage == "YELLOW" and all_red > 0:
                _set_phase_state(resolved_tl_id, phase, "ALL_RED", all_red)
                stage = "ALL_RED"
                timer = max(1, all_red)
                telemetry.record_phase_event(
                    step_index=step,
                    event_type="all_red_start",
                    phase_name=phase["name"],
                    phase_index=phase_idx,
                    stage=stage,
                    assigned_duration=timer,
                    actual_duration=None,
                    reason="clearance",
                    directions=phase["dirs"],
                )
            else:
                phase_idx = next_phase_idx
                phase = phase_plan[phase_idx]
                phase_queue = sum(q_dir.get(d, 0.0) for d in phase["dirs"])
                phase_flow = sum(flow_dir.get(d, 0.0) for d in phase["dirs"])
                phase_wait = sum(wait_sum_by_dir.get(d, 0.0) for d in phase["dirs"]) / max(step + 1, 1)
                if mode == "fuzzy":
                    fuzzy_green = _decide_green_duration(
                        mode=mode,
                        fuzzy=fuzzy,
                        weighted_by_dir=weighted_by_dir,
                        phase_dirs=phase["dirs"],
                        phase_queue=phase_queue,
                        phase_flow=phase_flow,
                        phase_wait=phase_wait,
                        red_age=red_age_by_phase[phase_idx],
                        min_green=min_green,
                        max_green=max_green,
                    )
                    phase_scores = _compute_phase_scores(
                        phase_plan=phase_plan,
                        weighted_by_dir=weighted_by_dir,
                        q_dir=q_dir,
                        flow_dir=flow_dir,
                        red_age_by_phase=red_age_by_phase,
                    )
                    score_now = phase_scores[phase_idx]
                    avg_score = sum(phase_scores) / max(len(phase_scores), 1)
                    ratio_green = int(round(22.0 * (score_now / max(avg_score, 1e-6))))
                    ratio_green = max(min_green, min(max_green, ratio_green))
                    starvation_boost = min(6, red_age_by_phase[phase_idx] // 24)
                    if len(phase_plan) == 2:
                        total_network_flow = sum(flow_dir.values())
                        total_network_queue = sum(q_dir.values())
                        phase_peak = _phase_direction_peak(phase, q_dir)
                        if total_network_flow <= 10.0 and total_network_queue <= 7.0:
                            current_green = max(min_green, min(max_green, max(min_green + 10, baseline_green - 8)))
                        else:
                            other_idx = _next_round_robin_phase_index(phase_plan, phase_idx)
                            other_phase = phase_plan[other_idx]
                            other_queue = _phase_queue_total(other_phase, q_dir)
                            other_flow = sum(flow_dir.get(d, 0.0) for d in other_phase["dirs"])
                            other_peak = _phase_direction_peak(other_phase, q_dir)
                            total_demand = max(
                                ((phase_queue * 2.4) + (phase_flow * 1.5))
                                + ((other_queue * 2.4) + (other_flow * 1.5)),
                                1e-6,
                            )
                            phase_demand = (phase_queue * 2.4) + (phase_flow * 1.5) + (min(red_age_by_phase[phase_idx], 60) * 0.12)
                            demand_share = phase_demand / total_demand
                            compact_baseline = max(min_green + 10, min(max_green, baseline_green - 8))
                            if step >= 600 or total_network_queue >= 12.0 or total_network_flow >= 14.0:
                                demand_share = max(0.36, min(0.64, demand_share))
                            else:
                                demand_share = max(0.40, min(0.60, demand_share))
                            share_green = compact_baseline + int(round((demand_share - 0.5) * 10.0))
                            queue_bias = int(round(max(-2.0, min(3.0, ((phase_queue - other_queue) * 0.28) + ((phase_peak - other_peak) * 0.18)))))
                            current_green = share_green + queue_bias + min(1, starvation_boost)
                            current_green = max(compact_baseline - 2, min(compact_baseline + 6, current_green))
                    else:
                        current_green = int(round((0.7 * fuzzy_green) + (0.3 * ratio_green) + starvation_boost))
                    current_green = min(current_green, max(min_green + 22, min(max_green, 44)))
                    current_green = max(min_green, min(max_green, current_green))
                else:
                    current_green = _decide_green_duration(
                        mode=mode,
                        fuzzy=fuzzy,
                        weighted_by_dir=weighted_by_dir,
                        phase_dirs=phase["dirs"],
                        phase_queue=phase_queue,
                        phase_flow=phase_flow,
                        phase_wait=phase_wait,
                        red_age=red_age_by_phase[phase_idx],
                        min_green=min_green,
                        max_green=max_green,
                    )
                _set_phase_state(resolved_tl_id, phase, "GREEN", current_green)
                stage = "GREEN"
                timer = current_green
                elapsed_green = 0
                telemetry.record_phase_event(
                    step_index=step,
                    event_type="green_start",
                    phase_name=phase["name"],
                    phase_index=phase_idx,
                    stage=stage,
                    assigned_duration=current_green,
                    actual_duration=None,
                    reason="next_phase_selected",
                    directions=phase["dirs"],
                )
    except Exception as exc:
        telemetry.complete({}, error_message=str(exc))
        DB.persist(telemetry)
        raise
    finally:
        traci.close()

    for direction in directions:
        if red_streak_by_dir[direction] > 0:
            red_samples_by_dir[direction].append(red_streak_by_dir[direction])
        if green_streak_by_dir[direction] > 0:
            green_samples_by_dir[direction].append(green_streak_by_dir[direction])

    avg_queue = sum(queue_series) / max(len(queue_series), 1)
    max_queue = max(queue_series) if queue_series else 0.0
    avg_wait = total_wait / max(duration_steps, 1)
    throughput_per_min = arrived_total / max(duration_steps / 60.0, 1e-6)
    density_index = avg_queue / 80.0
    fairness_gap = _fairness_gap(phase_plan, wait_sum_by_dir, duration_steps)
    all_red_samples = [sample for samples in red_samples_by_dir.values() for sample in samples]
    avg_red = sum(all_red_samples) / max(len(all_red_samples), 1)
    max_red = max(all_red_samples) if all_red_samples else 0.0
    direction_stats = _build_direction_stats(directions, green_samples_by_dir, red_samples_by_dir)

    result = {
        "kpi": {
            "avg_wait_s": round(avg_wait, 3),
            "avg_red_s": round(avg_red, 3),
            "max_red_s": round(max_red, 3),
            "max_queue": round(max_queue, 3),
            "avg_queue": round(avg_queue, 3),
            "throughput_per_min": round(throughput_per_min, 3),
            "density_index": round(density_index, 3),
            "phase_fairness_gap": round(fairness_gap, 3),
            "total_served": float(arrived_total),
        },
        "timeline": timeline,
        "phase_plan": phase_plan,
        "resolved_tl_id": resolved_tl_id,
    }
    telemetry.set_direction_stats(direction_stats)
    telemetry.complete(result["kpi"])
    DB.persist(telemetry)
    return result


def run_comparison_sumo(
    *,
    sumo_cfg: str,
    tl_id: str,
    intersection_type: str,
    weighted_by_dir: Dict[str, float],
    duration_steps: int = 1800,
    min_green: int = 10,
    max_green: int = 60,
    yellow: int = 3,
    all_red: int = 1,
    use_gui: bool = False,
    custom_fourway_logic: bool = True,
) -> Dict:
    comparison_group_id = str(uuid4())
    fixed = _run_single_mode(
        sumo_cfg=sumo_cfg,
        tl_id=tl_id,
        intersection_type=intersection_type,
        weighted_by_dir=weighted_by_dir,
        mode="fixed",
        duration_steps=duration_steps,
        min_green=min_green,
        max_green=max_green,
        yellow=yellow,
        all_red=all_red,
        use_gui=use_gui,
        custom_fourway_logic=custom_fourway_logic,
        comparison_group_id=comparison_group_id,
    )
    fuzzy = _run_single_mode(
        sumo_cfg=sumo_cfg,
        tl_id=tl_id,
        intersection_type=intersection_type,
        weighted_by_dir=weighted_by_dir,
        mode="fuzzy",
        duration_steps=duration_steps,
        min_green=min_green,
        max_green=max_green,
        yellow=yellow,
        all_red=all_red,
        use_gui=use_gui,
        custom_fourway_logic=custom_fourway_logic,
        comparison_group_id=comparison_group_id,
    )
    return {"fixed": fixed, "fuzzy": fuzzy}
