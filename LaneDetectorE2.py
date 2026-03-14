import traci

# Start your simulation
traci.start(["sumo-gui", "-c", "Test1.sumocfg", "-a", "Test1.add.xml"])

while traci.simulation.getMinExpectedNumber() > 0:
    traci.simulationStep()

    # 1. Get the current number of vehicles on the South detector
    count_south = traci.lanearea.getLastStepVehicleNumber("det_south")

    # 2. Get the current number of vehicles on the West detector
    count_west = traci.lanearea.getLastStepVehicleNumber("det_west")

    # Optional: Get the IDs of the specific vehicles if you need to track them
    veh_ids = traci.lanearea.getLastStepVehicleIDs("det_south")

    print(f"Step {traci.simulation.getTime()}: South={count_south}, West={count_west}")

traci.close()