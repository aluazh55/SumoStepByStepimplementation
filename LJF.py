import traci

# Constants for your specific network
TLS_ID = "J6"
PHASE_SOUTH_GREEN = 0  # Replace with your actual phase index
PHASE_WEST_GREEN = 2  # Replace with your actual phase index
DET_SOUTH = "det_south"
DET_WEST = "det_west"

traci.start(["sumo-gui", "-c", "Test1.sumocfg"])

while traci.simulation.getMinExpectedNumber() > 0:
    traci.simulationStep()

    # Get current counts
    count_south = traci.lanearea.getLastStepVehicleNumber(DET_SOUTH)
    count_west = traci.lanearea.getLastStepVehicleNumber(DET_WEST)

    # Determine which lane currently has green
    current_phase = traci.trafficlight.getPhase(TLS_ID)

    # Logic: If South has more cars and West isn't currently mid-green
    if count_south > count_west and count_south > 0:
        if current_phase != PHASE_SOUTH_GREEN:
            traci.trafficlight.setPhase(TLS_ID, PHASE_SOUTH_GREEN)

        # Hold this phase until South is empty
        while traci.lanearea.getLastStepVehicleNumber(DET_SOUTH) > 0:
            traci.simulationStep()
            # Optional: print status

    # Logic: If West has more cars (or South just finished)
    elif count_west > 0:
        if current_phase != PHASE_WEST_GREEN:
            traci.trafficlight.setPhase(TLS_ID, PHASE_WEST_GREEN)

        # Hold this phase until West is empty
        while traci.lanearea.getLastStepVehicleNumber(DET_WEST) > 0:
            traci.simulationStep()

traci.close()