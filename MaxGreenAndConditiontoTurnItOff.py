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

import os
import sys
import traci

# ... (Steps 1-5: Setup remains the same) ...

# Step 6: Define Variables
TLS_ID = "J6"
DET_SOUTH = "det_south"
DET_WEST = "det_west"

PHASE_SOUTH_GREEN = 0
PHASE_WEST_GREEN = 2

MAX_GREEN_STEPS = 60 / 0.05
YELLOW_STEPS = 3 / 0.05

# Tracking Variables
last_phase = traci.trafficlight.getPhase(TLS_ID)
last_change_time = traci.simulation.getTime()

MIN_GREEN_TIME = 10.0   # seconds - prevents instant flip-flop
MAX_GREEN_TIME = 60.0   # seconds
current_green_phase = traci.trafficlight.getPhase(TLS_ID)
green_start_time = traci.simulation.getTime()

# --- NEW: LOGGING FUNCTION ---
def log_combined_data():
    """Logs phase duration AND transport data at the moment of change."""
    global last_phase, last_change_time

    current_phase = traci.trafficlight.getPhase(TLS_ID)

    # Check if the traffic light phase changed
    if current_phase != last_phase:
        current_time = traci.simulation.getTime()
        duration = current_time - last_change_time

        # Transport Data Snapshot
        count_s = traci.lanearea.getLastStepVehicleNumber(DET_SOUTH)
        count_w = traci.lanearea.getLastStepVehicleNumber(DET_WEST)
        total_cars = traci.simulation.getMinExpectedNumber()

        # Log Output
        print(f"\n{'=' * 40}")
        print(f"EVENT: Traffic Light Phase Change")
        print(f"Time: {current_time:.2f}s | Ended Phase: {last_phase} | Duration: {duration:.2f}s")
        print(f"--- Transport Report ---")
        print(f"South Detector: {count_s} cars")
        print(f"West Detector:  {count_w} cars")
        print(f"Total in System: {total_cars} vehicles")
        print(f"{'=' * 40}")

        # Update trackers
        last_phase = current_phase
        last_change_time = current_time


def run_step():
    """Standardizes simulation steps so we never miss a log entry."""
    traci.simulationStep()
    log_combined_data()


# Step 7: Define Logic Functions
def switch_to_direction(target_green_phase):
    """Transitions to yellow, then to the target green."""
    current_p = traci.trafficlight.getPhase(TLS_ID)
    if current_p != target_green_phase:
        # Switch to Yellow
        traci.trafficlight.setPhase(TLS_ID, current_p + 1)
        for _ in range(int(YELLOW_STEPS)):
            run_step()  # Logging happens during yellow too

        # Switch to Green
        traci.trafficlight.setPhase(TLS_ID, target_green_phase)


# Force a clean starting green phase (optional but recommended)
if current_green_phase not in [PHASE_SOUTH_GREEN, PHASE_WEST_GREEN]:
    traci.trafficlight.setPhase(TLS_ID, PHASE_SOUTH_GREEN)
    current_green_phase = PHASE_SOUTH_GREEN
    green_start_time = traci.simulation.getTime()

# ==================== MAIN SIMULATION LOOP (replace the old one) ====================
while traci.simulation.getMinExpectedNumber() > 0:
    run_step()                      # advance + log

    c_south = traci.lanearea.getLastStepVehicleNumber(DET_SOUTH)
    c_west  = traci.lanearea.getLastStepVehicleNumber(DET_WEST)
    current_time = traci.simulation.getTime()

    print(f"DEBUG [{current_time:.2f}s] phase={traci.trafficlight.getPhase(TLS_ID)} "
          f"tracked_green={current_green_phase}  green_age={(current_time - green_start_time):.1f}s  "
          f"S:{c_south}  W:{c_west}")

    # === SOUTH is current green ===
    if current_green_phase == PHASE_SOUTH_GREEN:
        if (current_time - green_start_time >= MIN_GREEN_TIME) and \
           ((c_south == 0 and c_west > 0) or \
            (c_west > 0 and current_time - green_start_time >= MAX_GREEN_TIME)):
            switch_to_direction(PHASE_WEST_GREEN)
            current_green_phase = PHASE_WEST_GREEN
            green_start_time = traci.simulation.getTime()   # reset after yellow finishes

    # === WEST is current green ===
    else:  # WEST green
        if (current_time - green_start_time >= MIN_GREEN_TIME) and \
           ((c_west == 0 and c_south > 0) or \
            (c_south > 0 and current_time - green_start_time >= MAX_GREEN_TIME)):
            switch_to_direction(PHASE_SOUTH_GREEN)
            current_green_phase = PHASE_SOUTH_GREEN
            green_start_time = traci.simulation.getTime()

traci.close()