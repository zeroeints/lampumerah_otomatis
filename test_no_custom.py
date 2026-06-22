import sys
sys.path.insert(0, '.')
from sumo_simulation_opt import run_comparison_sumo

print("=== RUNNING COMPARISON WITH custom_fourway_logic = False ===")
weighted_by_dir = {
    "Utara": 30.0,
    "Selatan": 30.0,
    "Timur": 10.0,
    "Barat": 10.0
}

try:
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
        custom_fourway_logic=False  # Crucial change to use setPhase instead of setRedYellowGreenState
    )
    print("\n=== RESULTS ===")
    for mode in ["fixed", "fuzzy"]:
        kpi = results[mode]["kpi"]
        print(f"\nMode: {mode.upper()}")
        print(f"  Avg waiting time (s)   : {kpi['avg_wait_s']}")
        print(f"  Avg red-light dur (s)  : {kpi['avg_red_s']}")
        print(f"  Max red-light dur (s)  : {kpi['max_red_s']}")
        print(f"  Avg queue length       : {kpi['avg_queue']}")
        print(f"  Max queue length       : {kpi['max_queue']}")
        print(f"  Throughput / min       : {kpi['throughput_per_min']}")
        print(f"  Total served vehicles  : {kpi['total_served']}")
        
    fixed_wait = results["fixed"]["kpi"]["avg_wait_s"]
    fuzzy_wait = results["fuzzy"]["kpi"]["avg_wait_s"]
    improvement = ((fixed_wait - fuzzy_wait) / fixed_wait) * 100.0
    print(f"\nWaiting Time Improvement: {improvement:.2f}%")
    
except Exception as e:
    print(f"Error running simulation: {e}")
