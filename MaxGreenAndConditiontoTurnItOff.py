# Step 1: Add modules to provide access to specific libraries and functions
import os
import sys

# Step 2: Establish path to SUMO (SUMO_HOME)
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("Please declare environment variable 'SUMO_HOME'")

# Step 3: Add Traci module to provide access to specific libraries and functions
import traci

# Step 4: Define Sumo configuration
Sumo_config = [
    'sumo-gui',
    '-c', 'Test1.sumocfg',
    '--step-length', '0.05',
    '--delay', '50',
    '--start', 'true'
]

# Step 5: Open connection between SUMO and Traci
traci.start(Sumo_config)

# Step 6: Define Variables
TLS_ID = "J6"
DET_SOUTH = "det_south"
DET_WEST = "det_west"

PHASE_SOUTH_GREEN = 0
PHASE_WEST_GREEN = 2

MAX_GREEN_STEPS = 60 / 0.05
YELLOW_STEPS = 3 / 0.05


# Step 7: Define Functions
def switch_to_direction(target_green_phase):
    """Handles the transition to a green phase including yellow light."""
    current_phase = traci.trafficlight.getPhase(TLS_ID)

    if current_phase != target_green_phase:
        # Switch to Yellow (current + 1)
        traci.trafficlight.setPhase(TLS_ID, current_phase + 1)
        for _ in range(int(YELLOW_STEPS)):
            traci.simulationStep()

        # Switch to Green
        traci.trafficlight.setPhase(TLS_ID, target_green_phase)


# Step 8: Take simulation steps until there are no more vehicles in the network
while traci.simulation.getMinExpectedNumber() > 0:
    traci.simulationStep()

    count_south = traci.lanearea.getLastStepVehicleNumber(DET_SOUTH)
    count_west = traci.lanearea.getLastStepVehicleNumber(DET_WEST)

    # --- Case 1: South has priority or is the only one with cars ---
    if count_south > 0 and (count_south >= count_west or count_west == 0):
        switch_to_direction(PHASE_SOUTH_GREEN)

        timer = 0
        while traci.lanearea.getLastStepVehicleNumber(DET_SOUTH) > 0:
            traci.simulationStep()
            timer += 1

            # CHECK: Only enforce MAX_GREEN if West actually has cars waiting
            if traci.lanearea.getLastStepVehicleNumber(DET_WEST) > 0 and timer >= MAX_GREEN_STEPS:
                break

    # --- Case 2: West has priority or is the only one with cars ---
    elif count_west > 0:
        switch_to_direction(PHASE_WEST_GREEN)

        timer = 0
        while traci.lanearea.getLastStepVehicleNumber(DET_WEST) > 0:
            traci.simulationStep()
            timer += 1

            # CHECK: Only enforce MAX_GREEN if South actually has cars waiting
            if traci.lanearea.getLastStepVehicleNumber(DET_SOUTH) > 0 and timer >= MAX_GREEN_STEPS:
                break

# Step 9: Close connection between SUMO and Traci
traci.close()