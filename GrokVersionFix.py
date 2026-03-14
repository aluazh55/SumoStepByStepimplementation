import os
import sys

if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("Please declare environment variable 'SUMO_HOME'")

import traci

# ── Конфигурация ──────────────────────────────────────────────────────────────
TLS_ID = "J6"
DET_SOUTH = "det_south"
DET_WEST = "det_west"

# Считано из .net.xml
SIGNAL = {
    "SOUTH_GREEN": "GGrr",
    "SOUTH_YELLOW": "yyrr",
    "WEST_GREEN": "rrGG",
    "WEST_YELLOW": "rryy",
    "ALL_RED": "rrrr",
}

# Параметры
MIN_GREEN = 12  # минимальное время зелёного при наличии машин
MAX_GREEN = 50  # максимальное время зелёного
GAP_OUT_THRESHOLD = 0  # машин на текущей фазе для gap-out (обычно 0)
SWITCH_THRESHOLD = 5  # на сколько больше машин на противоположной фазе
HYSTERESIS = 2  # гистерезис для предотвращения дёрганья (можно 0)

IDLE_CYCLE_TIME = 20  # длительность пешеходного цикла
MIN_PEDESTRIAN_PROTECTION = 20  # защита пешеходного цикла от прерывания

YELLOW_DURATION = 3
ALL_RED_DURATION = 2
SIM_STEP = 0.1  # должно совпадать с --step-length в sumo


# ── Константы состояний ───────────────────────────────────────────────────────
class Phase:
    SOUTH = "SOUTH"
    WEST = "WEST"


class State:
    IDLE = "IDLE"
    ACTIVE = "ACTIVE"
    YELLOW = "YELLOW"
    ALL_RED = "ALL_RED"


# ── Контроллер ────────────────────────────────────────────────────────────────
class AdaptiveController:
    def __init__(self):
        self.current_phase = Phase.SOUTH
        self.next_phase = Phase.SOUTH
        self.state = State.IDLE
        self.timer = 0.0
        self.transition_timer = 0.0

    def step(self, count_south: int, count_west: int) -> dict:
        self.timer = round(self.timer + SIM_STEP, 2)

        if self.state == State.YELLOW:
            return self._handle_yellow()

        if self.state == State.ALL_RED:
            return self._handle_all_red(count_south, count_west)

        if self.state == State.IDLE:
            return self._handle_idle(count_south, count_west)

        if self.state == State.ACTIVE:
            return self._handle_active(count_south, count_west)

    # ── Состояние IDLE (пешеходный цикл) ──────────────────────────────────────
    def _handle_idle(self, cs: int, cw: int):
        has_cars = cs > 0 or cw > 0

        # Машины появились → ждём завершения пешеходной фазы
        if has_cars and self.timer < MIN_PEDESTRIAN_PROTECTION:
            rem = round(MIN_PEDESTRIAN_PROTECTION - self.timer)
            return self._result(f"Ped prot. {rem}s left")

        # Пешеходный цикл закончился
        if self.timer >= IDLE_CYCLE_TIME:
            if not has_cars:
                # Дорога пустая → тихо меняем направление
                self.current_phase = Phase.WEST if self.current_phase == Phase.SOUTH else Phase.SOUTH
                self.timer = 0.0
                return self._result(f"Idle swap → {self.current_phase}")

            # Есть машины → решаем, куда переключаться
            desired = self._choose_best_phase(cs, cw)
            if desired != self.current_phase:
                return self._start_transition(desired, "Idle → cars arrived")
            else:
                self.state = State.ACTIVE
                self.timer = 0.0
                return self._result(f"Idle → ACTIVE {self.current_phase} (cars already here)")

        return self._result(f"Ped green {round(self.timer)}/{IDLE_CYCLE_TIME}s")

    # ── Состояние ACTIVE (основное зелёное) ───────────────────────────────────
    def _handle_active(self, cs: int, cw: int):
        cur_count = cs if self.current_phase == Phase.SOUTH else cw
        opp_count = cw if self.current_phase == Phase.SOUTH else cs

        # Совсем пусто → сразу в IDLE
        if cur_count == 0 and opp_count == 0:
            self.state = State.IDLE
            self.timer = 0.0
            return self._result("No traffic → IDLE")

        # Min green — не даём переключаться
        if self.timer < MIN_GREEN:
            return self._result(f"Min green {round(self.timer, 1)}/{MIN_GREEN}s")

        # Условия переключения
        if cur_count <= GAP_OUT_THRESHOLD:
            return self._start_transition(self._opposite_phase(), "Gap-out")

        if self.timer >= MAX_GREEN:
            return self._start_transition(self._opposite_phase(), f"Max-out {round(self.timer)}s")

        # Противоположная фаза сильно перегружена
        if opp_count > cur_count + SWITCH_THRESHOLD + HYSTERESIS:
            opp = self._opposite_phase()
            return self._start_transition(opp, f"Threshold {opp}={opp_count} > {cur_count}+{SWITCH_THRESHOLD}")

        return self._result(f"Holding {self.current_phase}: {cur_count} vs {opp_count}")

    # ── Переходы ──────────────────────────────────────────────────────────────
    def _handle_yellow(self):
        self.transition_timer = round(self.transition_timer + SIM_STEP, 2)
        if self.transition_timer >= YELLOW_DURATION:
            self.state = State.ALL_RED
            self.transition_timer = 0.0
        return self._result(f"Yellow {round(self.transition_timer, 1)}/{YELLOW_DURATION}s")

    def _handle_all_red(self, cs: int, cw: int):
        self.transition_timer = round(self.transition_timer + SIM_STEP, 2)
        if self.transition_timer < ALL_RED_DURATION:
            return self._result(f"All-Red {round(self.transition_timer, 1)}/{ALL_RED_DURATION}s")

        # Переключаем фазу
        self.current_phase = self.next_phase
        self.timer = 0.0
        self.transition_timer = 0.0

        # Сразу смотрим, есть ли машины на новой фазе
        cur_count = cs if self.current_phase == Phase.SOUTH else cw
        if cur_count == 0:
            self.state = State.IDLE
            self.timer = 0.0
            return self._result("After switch: no cars → IDLE")
        else:
            self.state = State.ACTIVE
            return self._result(f"After switch → ACTIVE {self.current_phase}")

    def _start_transition(self, desired_phase: str, reason: str):
        self.next_phase = desired_phase
        self.state = State.YELLOW
        self.transition_timer = 0.0
        return self._result(f"{reason} → Yellow")

    # ── Вспомогательные методы ────────────────────────────────────────────────
    def _choose_best_phase(self, cs: int, cw: int) -> str:
        if cs > cw:
            return Phase.SOUTH
        if cw > cs:
            return Phase.WEST
        # равенство — продолжаем текущую или чередуем
        return Phase.WEST if self.current_phase == Phase.SOUTH else Phase.SOUTH

    def _opposite_phase(self) -> str:
        return Phase.WEST if self.current_phase == Phase.SOUTH else Phase.SOUTH

    def _result(self, reason: str) -> dict:
        if self.state in (State.YELLOW, State.ALL_RED):
            if self.state == State.YELLOW:
                sig_key = "SOUTH_YELLOW" if self.current_phase == Phase.SOUTH else "WEST_YELLOW"
            else:
                sig_key = "ALL_RED"
        else:
            sig_key = "SOUTH_GREEN" if self.current_phase == Phase.SOUTH else "WEST_GREEN"

        return {
            "signal": SIGNAL[sig_key],
            "state": self.state,
            "reason": reason
        }


# ── Запуск ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    sumo_cmd = [
        'sumo-gui',
        '-c', 'Test1.sumocfg',
        '--step-length', str(SIM_STEP),
        '--delay', '100',
    ]

    traci.start(sumo_cmd)
    controller = AdaptiveController()

    print("Сигналы:")
    for k, v in SIGNAL.items():
        print(f"  {k:15} : {v}")

    print("-" * 60)

    step = 0
    while traci.simulation.getMinExpectedNumber() > 0:
        traci.simulationStep()
        step += 1

        count_s = traci.lanearea.getLastStepVehicleNumber(DET_SOUTH)
        count_w = traci.lanearea.getLastStepVehicleNumber(DET_WEST)

        result = controller.step(count_s, count_w)
        traci.trafficlight.setRedYellowGreenState(TLS_ID, result["signal"])

        # вывод каждую секунду
        t = traci.simulation.getTime()
        if abs(t - round(t)) < 0.01:
            print(f"t={t:6.1f}s | {result['state']:8} | "
                  f"sig={result['signal']} | S={count_s} W={count_w} | {result['reason']}")

    traci.close()