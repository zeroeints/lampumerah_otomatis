import sys
sys.path.insert(0, '.')
import os
import traci

# We will start traci and check the links and states of J_center
SUMO_HOME = os.environ.get("SUMO_HOME", "")
tools = os.path.join(SUMO_HOME, "tools")
sys.path.append(tools)

sumo_bin = os.path.join(SUMO_HOME, "bin", "sumo.exe")
cmd = [sumo_bin, "-c", "sumo_config/intersection.sumocfg", "--no-warnings"]
traci.start(cmd)

tl_id = "J_center"
print("=== TRAFFIC LIGHT LINKS FOR J_center ===")
links = traci.trafficlight.getControlledLinks(tl_id)
for idx, link in enumerate(links):
    print(f"Link {idx}: {link}")

print("\n=== CURRENT PROGRAM LOGICS ===")
logics = traci.trafficlight.getAllProgramLogics(tl_id)
for logic in logics:
    print(f"Program: {logic.programID}, Type: {logic.type}")
    for p_idx, phase in enumerate(logic.phases):
        print(f"  Phase {p_idx}: duration={phase.duration}, state={phase.state}, name={phase.name}")

traci.close()
