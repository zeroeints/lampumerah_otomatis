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
cycles = []
current_cycle = None
last_phase = None
last_status = None

for entry in fuzzy_timeline:
    phase = entry["phase"]
    status = entry["status"]
    
    if phase != last_phase or status != last_status:
        if status == "GREEN":
            if current_cycle:
                cycles.append(current_cycle)
            current_cycle = {
                "phase": phase,
                "start_step": entry["step"],
                "assigned_duration": entry["green_time"],
                "actual_duration": 0,
                "end_step": None,
                "end_phase_queue": None,
                "end_other_queue": None,
            }
        last_phase = phase
        last_status = status
        
    if current_cycle and status == "GREEN" and phase == current_cycle["phase"]:
        current_cycle["actual_duration"] += 1
        current_cycle["end_step"] = entry["step"]
        current_cycle["end_phase_queue"] = entry["phase_queue"]

if current_cycle:
    cycles.append(current_cycle)

print("=== FUZZY CYCLES SUMMARY ===")
print(f"{'Phase':<10} {'Start':>6} {'End':>6} {'Assigned':>8} {'Actual':>8} {'End Queue':>10}")
print("-" * 55)
for c in cycles[:30]:  # print first 30 cycles
    print(f"{c['phase']:<10} {c['start_step']:>6} {c['end_step']:>6} {c['assigned_duration']:>8}s {c['actual_duration']:>8}s {c['end_phase_queue']:>10.1f}")
