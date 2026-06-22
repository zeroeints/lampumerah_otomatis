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
    custom_fourway_logic=False
)

fuzzy_timeline = results["fuzzy"]["timeline"]
print("=== DETAILED STEP-BY-STEP QUEUE FOR FUZZY NO CUSTOM ===")
print(f"{'Step':>6} {'NS Queue':>10} {'EW Queue':>10} {'Phase':<12} {'Status':<10}")
print("-" * 52)
for entry in fuzzy_timeline[500:570]:
    print(f"{entry['step']:>6} {entry['phase_queue']:>10.1f} {entry['queue_total'] - entry['phase_queue']:>10.1f} {entry['phase']:<12} {entry['status']:<10}")
