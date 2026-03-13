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

MAX_GREEN_STEPS = 60 / 0.05  # 60 seconds / step_length
YELLOW_STEPS = 3 / 0.05  # 3 seconds / step_length

# Logging variables
last_phase = traci.trafficlight.getPhase(TLS_ID)
last_change_time = traci.simulation.getTime()


def log_phase_duration():
    """Calculates and prints the duration of the phase that just ended."""
    global last_phase, last_change_time

    current_phase = traci.trafficlight.getPhase(TLS_ID)

    # Check if the phase has actually changed
    if current_phase != last_phase:
        current_time = traci.simulation.getTime()
        duration = current_time - last_change_time

        # Get the state string (e.g., "GrGr") to identify color if needed
        state = traci.trafficlight.getRedYellowGreenState(TLS_ID)

        print(f"Phase {last_phase} ended. Duration: {duration:.2f} seconds. (State: {state})")

        # Update trackers
        last_phase = current_phase
        last_change_time = current_time


def step_sim(steps=1):
    """Custom step function to ensure we check for phase changes every step."""
    for _ in range(steps):
        traci.simulationStep()
        log_phase_duration()


# Step 7: Define Functions (Modified to use our step_sim)
def switch_to_direction(target_green_phase):
    current_phase = traci.trafficlight.getPhase(TLS_ID)
    if current_phase != target_green_phase:
        # Switch to Yellow
        traci.trafficlight.setPhase(TLS_ID, current_phase + 1)
        step_sim(int(YELLOW_STEPS))

        # Switch to Green
        traci.trafficlight.setPhase(TLS_ID, target_green_phase)


# Step 8: Simulation Loop
while traci.simulation.getMinExpectedNumber() > 0:
    step_sim()  # Replaced traci.simulationStep()

    count_south = traci.lanearea.getLastStepVehicleNumber(DET_SOUTH)
    count_west = traci.lanearea.getLastStepVehicleNumber(DET_WEST)

    if count_south > 0 and (count_south >= count_west or count_west == 0):
        switch_to_direction(PHASE_SOUTH_GREEN)
        timer = 0
        while traci.lanearea.getLastStepVehicleNumber(DET_SOUTH) > 0:
            step_sim()
            timer += 1
            if traci.lanearea.getLastStepVehicleNumber(DET_WEST) > 0 and timer >= MAX_GREEN_STEPS:
                break

    elif count_west > 0:
        switch_to_direction(PHASE_WEST_GREEN)
        timer = 0
        while traci.lanearea.getLastStepVehicleNumber(DET_WEST) > 0:
            step_sim()
            timer += 1
            if traci.lanearea.getLastStepVehicleNumber(DET_SOUTH) > 0 and timer >= MAX_GREEN_STEPS:
                break

traci.close()