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

# Print events for FIXED
print("=== FIXED MODE EVENTS ===")
fixed_timeline = results["fixed"]["timeline"]
last_phase = None
last_status = None
for entry in fixed_timeline:
    phase = entry["phase"]
    status = entry["status"]
    if phase != last_phase or status != last_status:
        if status == "GREEN":
            print(f"Step {entry['step']}: Phase {phase} {status} (duration: {entry['green_time']}s, queue: {entry['phase_queue']:.1f})")
        else:
            print(f"Step {entry['step']}: Phase {phase} {status}")
        last_phase = phase
        last_status = status

# Print events for FUZZY
print("\n=== FUZZY MODE EVENTS ===")
fuzzy_timeline = results["fuzzy"]["timeline"]
last_phase = None
last_status = None
for entry in fuzzy_timeline:
    phase = entry["phase"]
    status = entry["status"]
    if phase != last_phase or status != last_status:
        if status == "GREEN":
            print(f"Step {entry['step']}: Phase {phase} {status} (duration: {entry['green_time']}s, queue: {entry['phase_queue']:.1f}, score: {entry['phase_score']})")
        else:
            print(f"Step {entry['step']}: Phase {phase} {status}")
        last_phase = phase
        last_status = status
