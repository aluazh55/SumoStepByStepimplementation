import os
import sys

if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("Please declare environment variable 'SUMO_HOME'")

import traci

# ── Конфиг ────────────────────────────────────────────────────────────────────
TLS_ID    = "J6"
DET_SOUTH = "det_south"
DET_WEST  = "det_west"

# ── Строки сигналов (не индексы фаз, а прямые строки) ─────────────────────────
#
#   Считано из твоего .net.xml:
#     Phase 0: GGrr  <- SOUTH green
#     Phase 1: yyrr  <- SOUTH yellow
#     Phase 2: rrGG  <- WEST green
#     Phase 3: rryy  <- WEST yellow
#
#   All-Red в .net.xml нет — задаём строку вручную.
#   setRedYellowGreenState принимает произвольную строку,
#   не обязательно из существующих фаз.
#
SIGNAL = {
    "SOUTH_GREEN":  "GGrr",
    "SOUTH_YELLOW": "yyrr",
    "ALL_RED":      "rrrr",  # нет в .net.xml, но работает напрямую
    "WEST_GREEN":   "rrGG",
    "WEST_YELLOW":  "rryy",
}

# ── Параметры контроллера ─────────────────────────────────────────────────────
MIN_GREEN        = 12
MAX_GREEN        = 50
THRESHOLD        = 5
IDLE_TIMEOUT     = 20
MIN_PED          = 20
YELLOW_DURATION  = 3
ALL_RED_DURATION = 2
SIM_STEP_VAL     = 0.05


# ── Классы ────────────────────────────────────────────────────────────────────
class Phase:
    C = "SOUTH"
    D = "WEST"

class ControllerState:
    IDLE    = "IDLE"
    ACTIVE  = "ACTIVE"
    YELLOW  = "YELLOW"
    ALL_RED = "ALL_RED"


class AdaptiveController:
    def __init__(self):
        self.current_phase    = Phase.C
        self.next_phase       = Phase.C
        self.state            = ControllerState.IDLE
        self.timer            = 0.0
        self.transition_timer = 0.0

    def step(self, count_c: int, count_d: int) -> dict:
        self.timer = round(self.timer + SIM_STEP_VAL, 2)

        if self.state == ControllerState.YELLOW:
            return self._handle_yellow()
        if self.state == ControllerState.ALL_RED:
            return self._handle_all_red()
        if self.state == ControllerState.IDLE:
            return self._handle_idle(count_c, count_d)
        if self.state == ControllerState.ACTIVE:
            return self._handle_active(count_c, count_d)

    # ── IDLE ──────────────────────────────────────────────────────────────────
    def _handle_idle(self, count_c, count_d):
        car_waiting = count_c > 0 or count_d > 0

        if car_waiting and self.timer < MIN_PED:
            rem = round(MIN_PED - self.timer)
            return self._result(f"Pedestrian protection ({rem}s left)")

        if self.timer >= IDLE_TIMEOUT or car_waiting:
            if count_c > count_d:
                self.next_phase = Phase.C
            elif count_d > count_c:
                self.next_phase = Phase.D
            else:
                self.next_phase = Phase.D if self.current_phase == Phase.C else Phase.C

            if self.next_phase != self.current_phase:
                return self._start_transition("Idle timeout / car arrival")
            else:
                self.state = ControllerState.ACTIVE
                self.timer = 0.0
                return self._result(f"-> ACTIVE {self.current_phase}")

        return self._result(f"Pedestrian green ({round(self.timer)}/{IDLE_TIMEOUT}s)")

    # ── ACTIVE ────────────────────────────────────────────────────────────────
    def _handle_active(self, count_c, count_d):
        cur_vol = count_c if self.current_phase == Phase.C else count_d
        opp_vol = count_d if self.current_phase == Phase.C else count_c

        if self.timer < MIN_GREEN:
            return self._result(f"Min_Green ({round(self.timer)}/{MIN_GREEN}s)")

        if cur_vol == 0 and opp_vol == 0:
            self.state = ControllerState.IDLE
            self.timer = 0.0
            return self._result("No traffic -> Idle")

        if cur_vol == 0:
            return self._start_transition(f"Gap-out: {self.current_phase} empty")
        if self.timer >= MAX_GREEN:
            return self._start_transition(f"Max-out: {round(self.timer)}s >= {MAX_GREEN}s")
        if opp_vol > cur_vol + THRESHOLD:
            opp = Phase.D if self.current_phase == Phase.C else Phase.C
            return self._start_transition(
                f"Threshold: {opp}={opp_vol} > {self.current_phase}={cur_vol}+{THRESHOLD}"
            )

        return self._result(f"Holding {self.current_phase}: {cur_vol} vs {opp_vol}")

    # ── YELLOW ────────────────────────────────────────────────────────────────
    def _handle_yellow(self):
        self.transition_timer = round(self.transition_timer + SIM_STEP_VAL, 2)
        if self.transition_timer >= YELLOW_DURATION:
            self.state            = ControllerState.ALL_RED
            self.transition_timer = 0.0
        return self._result(
            f"Yellow ({round(self.transition_timer, 1)}/{YELLOW_DURATION}s)"
        )

    # ── ALL_RED ───────────────────────────────────────────────────────────────
    def _handle_all_red(self):
        self.transition_timer = round(self.transition_timer + SIM_STEP_VAL, 2)
        if self.transition_timer >= ALL_RED_DURATION:
            self.current_phase    = self.next_phase
            self.state            = ControllerState.ACTIVE
            self.timer            = 0.0
            self.transition_timer = 0.0
        return self._result(
            f"All-Red ({round(self.transition_timer, 1)}/{ALL_RED_DURATION}s)"
        )

    # ── Утилиты ───────────────────────────────────────────────────────────────
    def _start_transition(self, reason: str) -> dict:
        self.next_phase       = Phase.D if self.current_phase == Phase.C else Phase.C
        self.state            = ControllerState.YELLOW
        self.transition_timer = 0.0
        return self._result(reason + " -> Yellow")

    def _result(self, reason: str) -> dict:
        s = self.state
        p = self.current_phase

        if s == ControllerState.YELLOW:
            signal = SIGNAL["SOUTH_YELLOW"] if p == Phase.C else SIGNAL["WEST_YELLOW"]
        elif s == ControllerState.ALL_RED:
            signal = SIGNAL["ALL_RED"]
        else:
            signal = SIGNAL["SOUTH_GREEN"] if p == Phase.C else SIGNAL["WEST_GREEN"]

        return {"signal": signal, "state": s, "reason": reason}


# ── Запуск ────────────────────────────────────────────────────────────────────
Sumo_config = [
    'sumo-gui', '-c', 'Test1.sumocfg',
    '--step-length', str(SIM_STEP_VAL),
    '--delay', '100',
]

traci.start(Sumo_config)
controller = AdaptiveController()

print("── Строки сигналов ──────────────────────────────────")
for name, sig in SIGNAL.items():
    print(f"  {name:15}: {sig}")
print("─────────────────────────────────────────────────────")

while traci.simulation.getMinExpectedNumber() > 0:
    traci.simulationStep()

    count_s = traci.lanearea.getLastStepVehicleNumber(DET_SOUTH)
    count_w = traci.lanearea.getLastStepVehicleNumber(DET_WEST)

    res = controller.step(count_s, count_w)

    # Напрямую задаём строку сигнала — SUMO только отображает
    traci.trafficlight.setRedYellowGreenState(TLS_ID, res["signal"])

    if traci.simulation.getTime() % 1 == 0:
        print(
            f"t={traci.simulation.getTime():6.1f}s | "
            f"{res['state']:8} | "
            f"signal={res['signal']} | "
            f"S={count_s} W={count_w} | "
            f"{res['reason']}"
        )

traci.close()