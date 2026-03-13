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
    '--step-length', '0.05',  # High precision (20 steps per second)
    '--delay', '50',  # Reduced delay for smoother visualization
    '--start', 'true'  # Start the simulation automatically
]

# Step 5: Open connection between SUMO and Traci
traci.start(Sumo_config)

# Step 6: Define Variables
TLS_ID = "J6"  # Change to your TLS ID
DET_SOUTH = "det_south"  # Change to your E2 ID
DET_WEST = "det_west"  # Change to your E2 ID

PHASE_SOUTH_GREEN = 0
PHASE_SOUTH_YELLOW = 1
PHASE_WEST_GREEN = 2
PHASE_WEST_YELLOW = 3

MAX_GREEN_STEPS = 60 / 0.05  # 60 seconds / step_length
YELLOW_STEPS = 3 / 0.05  # 3 seconds / step_length


# Step 7: Define Functions
def switch_to_direction(target_green_phase):
    """Handles the transition to a green phase including yellow light."""
    current_phase = traci.trafficlight.getPhase(TLS_ID)

    if current_phase != target_green_phase:
        # 1. Switch to Yellow (Assumes yellow is current_phase + 1)
        traci.trafficlight.setPhase(TLS_ID, current_phase + 1)
        for _ in range(int(YELLOW_STEPS)):
            traci.simulationStep()

        # 2. Switch to Green
        traci.trafficlight.setPhase(TLS_ID, target_green_phase)


# Step 8: Take simulation steps until there are no more vehicles in the network
while traci.simulation.getMinExpectedNumber() > 0:
    traci.simulationStep()

    # Get current counts from E2 Detectors
    count_south = traci.lanearea.getLastStepVehicleNumber(DET_SOUTH)
    count_west = traci.lanearea.getLastStepVehicleNumber(DET_WEST)

    # Decision Logic
    if count_south >= count_west and count_south > 0:
        switch_to_direction(PHASE_SOUTH_GREEN)

        # Hold Green until lane is empty OR Max Green reached
        timer = 0
        while traci.lanearea.getLastStepVehicleNumber(DET_SOUTH) > 0 and timer < MAX_GREEN_STEPS:
            traci.simulationStep()
            timer += 1

    elif count_west > 0:
        switch_to_direction(PHASE_WEST_GREEN)

        # Hold Green until lane is empty OR Max Green reached
        timer = 0
        while traci.lanearea.getLastStepVehicleNumber(DET_WEST) > 0 and timer < MAX_GREEN_STEPS:
            traci.simulationStep()
            timer += 1

# Step 9: Close connection between SUMO and Traci
traci.close()