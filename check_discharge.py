import sys
sys.path.insert(0, '.')
from sumo_simulation_opt import run_comparison_sumo

weighted_by_dir = {
    "Utara": 30.0,
    "Selatan": 30.0,
    "Timur": 10.0,
    "Barat": 10.0
}

results = run_comparison_sumo(
    sumo_cfg="sumo_config/intersection.sumocfg",
    tl_id="J_center",
    intersection_type="Perempatan",
    weighted_by_dir=weighted_by_dir,
    duration_steps=1800,
    min_green=10,
    max_green=60,
    yellow=3,
    all_red=1,
    use_gui=False,
    custom_fourway_logic=True
)

fuzzy_timeline = results["fuzzy"]["timeline"]
# Find the start and end of a specific NS_MAIN GREEN phase (e.g. the one starting around step 527)
print("=== DETAILED STEP-BY-STEP QUEUE FOR NS_MAIN GREEN (steps 527-564) ===")
print(f"{'Step':>6} {'NS Queue':>10} {'EW Queue':>10}")
print("-" * 32)
for entry in fuzzy_timeline:
    step = entry["step"]
    if 527 <= step <= 566:
        # We need to compute EW queue to display, let's look at the database or other values if we can.
        # But we only have entry["phase_queue"] which is NS queue when phase is NS_MAIN, and EW queue when phase is EW_MAIN.
        # Let's see if we can get direction state or other things. Wait, the timeline entry in _run_single_mode has:
        # "queue_total": q_now, "phase_queue": phase_queue, etc.
        # Let's print those.
        print(f"{step:>6} {entry['phase_queue']:>10.1f} {entry['queue_total'] - entry['phase_queue']:>10.1f} | Phase: {entry['phase']} ({entry['status']})")
