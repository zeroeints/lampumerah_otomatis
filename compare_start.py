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

fixed = results["fixed"]["timeline"]
fuzzy = results["fuzzy"]["timeline"]

print("=== START OF SIMULATION COMPARISON (Steps 0-300) ===")
print(f"{'Step':>5} | {'FIXED Phase':<12} {'FIXED Status':<8} {'FIXED Q':>5} | {'FUZZY Phase':<12} {'FUZZY Status':<8} {'FUZZY Q':>5}")
print("-" * 80)
for i in range(0, 300, 10):
    fx = fixed[i]
    fz = fuzzy[i]
    print(f"{fx['step']:>5} | {fx['phase']:<12} {fx['status']:<8} {fx['queue_total']:>5.1f} | {fz['phase']:<12} {fz['status']:<8} {fz['queue_total']:>5.1f}")
