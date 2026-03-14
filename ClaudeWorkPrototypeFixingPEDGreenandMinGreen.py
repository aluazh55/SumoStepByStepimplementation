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

# ── Строки сигналов ───────────────────────────────────────────────────────────
#   Считано из .net.xml:
#     Phase 0: GGrr  <- SOUTH green
#     Phase 1: yyrr  <- SOUTH yellow
#     Phase 2: rrGG  <- WEST green
#     Phase 3: rryy  <- WEST yellow
#   All-Red задаём вручную — в .net.xml его нет.
SIGNAL = {
    "SOUTH_GREEN":  "GGrr",
    "SOUTH_YELLOW": "yyrr",
    "ALL_RED":      "rrrr",
    "WEST_GREEN":   "rrGG",
    "WEST_YELLOW":  "rryy",
}

# ── Параметры контроллера ─────────────────────────────────────────────────────
MIN_GREEN        = 12   # с — Min_Green активен ТОЛЬКО при наличии машин
MAX_GREEN        = 50   # с
THRESHOLD        = 5    # машин
IDLE_TIMEOUT     = 20   # с — длительность пешеходного цикла
MIN_PED          = 20   # с — защита пешеходного цикла от прерывания
YELLOW_DURATION  = 3    # с
ALL_RED_DURATION = 2    # с
SIM_STEP_VAL     = 0.05 # с


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
            # ← передаём счётчики чтобы решить куда идти после перехода
            return self._handle_all_red(count_c, count_d)
        if self.state == ControllerState.IDLE:
            return self._handle_idle(count_c, count_d)
        if self.state == ControllerState.ACTIVE:
            return self._handle_active(count_c, count_d)

    # ── IDLE ──────────────────────────────────────────────────────────────────
    #
    #   Два сценария:
    #   1. Дорога пустая — крутим пешеходный цикл 20с, тихо чередуем фазы.
    #      Yellow и All-Red НЕ нужны — предупреждать некого.
    #   2. Появились машины — ждём до MIN_PED, потом запускаем переход.
    #
    def _handle_idle(self, count_c, count_d):
        car_waiting = count_c > 0 or count_d > 0

        # Машины появились, но пешеходный цикл ещё не завершён — ждём
        if car_waiting and self.timer < MIN_PED:
            rem = round(MIN_PED - self.timer)
            return self._result(f"Pedestrian protection ({rem}s left)")

        # Пешеходный цикл завершён
        if self.timer >= IDLE_TIMEOUT:
            if not car_waiting:
                # Дорога пустая — тихо меняем фазу, без Yellow/All-Red
                self.current_phase = Phase.D if self.current_phase == Phase.C else Phase.C
                self.next_phase    = self.current_phase
                self.timer         = 0.0
                return self._result(f"Pedestrian swap -> {self.current_phase}")

            # Машины есть — выбираем нужную фазу и запускаем переход
            if count_c > count_d:
                self.next_phase = Phase.C
            elif count_d > count_c:
                self.next_phase = Phase.D
            else:
                self.next_phase = Phase.D if self.current_phase == Phase.C else Phase.C

            if self.next_phase != self.current_phase:
                return self._start_transition("Idle timeout / car arrival")
            else:
                # Машины уже на текущей фазе — сразу ACTIVE
                self.state = ControllerState.ACTIVE
                self.timer = 0.0
                return self._result(f"-> ACTIVE {self.current_phase}")

        return self._result(f"Pedestrian green ({round(self.timer)}/{IDLE_TIMEOUT}s)")

    # ── ACTIVE ────────────────────────────────────────────────────────────────
    #
    #   Порядок проверок важен:
    #   1. Сначала — пустая дорога → сразу IDLE (Min_Green не блокирует).
    #   2. Потом  — Min_Green (только если машины есть).
    #   3. Потом  — условия переключения.
    #
    def _handle_active(self, count_c, count_d):
        cur_vol = count_c if self.current_phase == Phase.C else count_d
        opp_vol = count_d if self.current_phase == Phase.C else count_c

        # Дорога пустая — Min_Green не нужен, сразу в IDLE
        if cur_vol == 0 and opp_vol == 0:
            self.state = ControllerState.IDLE
            self.timer = 0.0
            return self._result("No traffic -> Idle")

        # Min_Green — блокируем переключение (машины точно есть)
        if self.timer < MIN_GREEN:
            return self._result(f"Min_Green ({round(self.timer)}/{MIN_GREEN}s)")

        # Условия переключения
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
    #
    #   После перехода решаем куда идти на основе текущего трафика:
    #   · Есть машины → ACTIVE
    #   · Нет машин   → IDLE (пешеходный цикл, без Min_Green)
    #
    def _handle_all_red(self, count_c, count_d):
        self.transition_timer = round(self.transition_timer + SIM_STEP_VAL, 2)
        if self.transition_timer >= ALL_RED_DURATION:
            self.current_phase    = self.next_phase
            self.timer            = 0.0
            self.transition_timer = 0.0

            # ← ключевой фикс: не всегда ACTIVE после перехода
            if count_c == 0 and count_d == 0:
                self.state = ControllerState.IDLE
            else:
                self.state = ControllerState.ACTIVE

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
            # IDLE и ACTIVE — горит зелёный текущей фазы
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