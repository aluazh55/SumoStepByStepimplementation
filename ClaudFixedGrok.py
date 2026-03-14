import os
import sys

if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("Please declare environment variable 'SUMO_HOME'")

import traci

# ── Конфигурация ──────────────────────────────────────────────────────────────
TLS_ID    = "J6"
DET_SOUTH = "det_south"
DET_WEST  = "det_west"

# Считано из .net.xml:
#   Phase 0: GGrr  <- SOUTH green
#   Phase 1: yyrr  <- SOUTH yellow
#   Phase 2: rrGG  <- WEST green
#   Phase 3: rryy  <- WEST yellow
#   All-Red задаём вручную — в .net.xml его нет
SIGNAL = {
    "SOUTH_GREEN":  "GGrr",
    "SOUTH_YELLOW": "yyrr",
    "WEST_GREEN":   "rrGG",
    "WEST_YELLOW":  "rryy",
    "ALL_RED":      "rrrr",
}

# ── Параметры контроллера ─────────────────────────────────────────────────────
MIN_GREEN    = 12   # с — минимальное время зелёного (активно ТОЛЬКО при наличии машин)
MAX_GREEN    = 50   # с — максимальное время зелёного
THRESHOLD    = 5    # машин — порог перегрузки оппозитной фазы
HYSTERESIS   = 0    # доп. запас к порогу (начни с 0, увеличивай по результатам)

# MIN_PEDESTRIAN_PROTECTION == IDLE_CYCLE_TIME намеренно:
# машины не могут прервать пешеходный цикл раньше его завершения
IDLE_CYCLE_TIME             = 20  # с — длительность пешеходного цикла
MIN_PEDESTRIAN_PROTECTION   = 20  # с — защита цикла от прерывания

YELLOW_DURATION  = 3    # с
ALL_RED_DURATION = 2    # с
SIM_STEP         = 0.1  # с — должно совпадать с --step-length в .sumocfg


# ── Константы ─────────────────────────────────────────────────────────────────
class Phase:
    SOUTH = "SOUTH"
    WEST  = "WEST"

class State:
    IDLE    = "IDLE"
    ACTIVE  = "ACTIVE"
    YELLOW  = "YELLOW"
    ALL_RED = "ALL_RED"


# ── Контроллер ────────────────────────────────────────────────────────────────
class AdaptiveController:
    def __init__(self):
        self.current_phase    = Phase.SOUTH
        self.next_phase       = Phase.SOUTH
        self.state            = State.IDLE
        self.timer            = 0.0
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

    # ── IDLE ──────────────────────────────────────────────────────────────────
    #
    #   Пока дорога пустая — крутим пешеходные циклы по 20с,
    #   тихо чередуя фазы без Yellow/All-Red (предупреждать некого).
    #   Как только машины появились И цикл завершён — уходим в ACTIVE.
    #
    def _handle_idle(self, cs: int, cw: int):
        has_cars = cs > 0 or cw > 0

        # Машины появились, но пешеходный цикл ещё не завершён — ждём
        if has_cars and self.timer < MIN_PEDESTRIAN_PROTECTION:
            rem = round(MIN_PEDESTRIAN_PROTECTION - self.timer)
            return self._result(f"Ped protection {rem}s left")

        # Пешеходный цикл завершён
        if self.timer >= IDLE_CYCLE_TIME:
            if not has_cars:
                # Дорога пустая — тихо меняем фазу без Yellow/All-Red
                self.current_phase = self._opposite_phase()
                self.next_phase    = self.current_phase
                self.timer         = 0.0
                return self._result(f"Idle swap -> {self.current_phase}")

            # Есть машины — выбираем нужную фазу
            desired = self._choose_best_phase(cs, cw)
            if desired != self.current_phase:
                return self._start_transition(desired, "Idle -> cars")
            else:
                # Машины уже на текущей фазе — сразу ACTIVE без перехода
                self.state = State.ACTIVE
                self.timer = 0.0
                return self._result(f"Idle -> ACTIVE {self.current_phase}")

        return self._result(f"Ped green {round(self.timer)}/{IDLE_CYCLE_TIME}s")

    # ── ACTIVE ────────────────────────────────────────────────────────────────
    #
    #   Порядок проверок принципиален:
    #   1. Пустая дорога → IDLE мгновенно, Min_Green не блокирует.
    #   2. Min_Green → блокируем переключение (машины точно есть).
    #   3. Условия переключения.
    #
    def _handle_active(self, cs: int, cw: int):
        cur_count = cs if self.current_phase == Phase.SOUTH else cw
        opp_count = cw if self.current_phase == Phase.SOUTH else cs

        # Дорога полностью пустая — Min_Green не нужен
        if cur_count == 0 and opp_count == 0:
            self.state = State.IDLE
            self.timer = 0.0
            return self._result("No traffic -> IDLE")

        # Min_Green — переключение заблокировано
        if self.timer < MIN_GREEN:
            return self._result(f"Min green {round(self.timer, 1)}/{MIN_GREEN}s")

        # Gap-out: текущая фаза опустела, оппозит ждёт
        if cur_count == 0:
            return self._start_transition(
                self._opposite_phase(),
                f"Gap-out: {self.current_phase} empty"
            )

        # Max-out: время вышло
        if self.timer >= MAX_GREEN:
            return self._start_transition(
                self._opposite_phase(),
                f"Max-out {round(self.timer)}s"
            )

        # Threshold: оппозит значительно перегружен
        if opp_count > cur_count + THRESHOLD + HYSTERESIS:
            opp = self._opposite_phase()
            return self._start_transition(
                opp,
                f"Threshold: {opp}={opp_count} > {self.current_phase}={cur_count}+{THRESHOLD}"
            )

        return self._result(f"Holding {self.current_phase}: {cur_count} vs {opp_count}")

    # ── YELLOW ────────────────────────────────────────────────────────────────
    def _handle_yellow(self):
        self.transition_timer = round(self.transition_timer + SIM_STEP, 2)
        if self.transition_timer >= YELLOW_DURATION:
            self.state            = State.ALL_RED
            self.transition_timer = 0.0
        return self._result(
            f"Yellow {round(self.transition_timer, 1)}/{YELLOW_DURATION}s"
        )

    # ── ALL_RED ───────────────────────────────────────────────────────────────
    #
    #   ИСПРАВЛЕНИЕ: проверяем ВЕСЬ трафик (cs + cw), а не только новую фазу.
    #   Иначе: переключились на WEST(0), но SOUTH=7 → ушли бы в IDLE
    #   и машины SOUTH ждали бы полный пешеходный цикл впустую.
    #
    def _handle_all_red(self, cs: int, cw: int):
        self.transition_timer = round(self.transition_timer + SIM_STEP, 2)
        if self.transition_timer < ALL_RED_DURATION:
            return self._result(
                f"All-Red {round(self.transition_timer, 1)}/{ALL_RED_DURATION}s"
            )

        # Переключаем фазу
        self.current_phase    = self.next_phase
        self.timer            = 0.0
        self.transition_timer = 0.0

        # Смотрим на ВЕСЬ трафик, а не только на новую фазу
        if cs == 0 and cw == 0:
            self.state = State.IDLE
            return self._result("After switch: no cars -> IDLE")
        else:
            self.state = State.ACTIVE
            return self._result(f"After switch -> ACTIVE {self.current_phase}")

    # ── Утилиты ───────────────────────────────────────────────────────────────
    def _opposite_phase(self) -> str:
        return Phase.WEST if self.current_phase == Phase.SOUTH else Phase.SOUTH

    def _choose_best_phase(self, cs: int, cw: int) -> str:
        if cs > cw:
            return Phase.SOUTH
        if cw > cs:
            return Phase.WEST
        # При равном трафике — чередуем
        return Phase.WEST if self.current_phase == Phase.SOUTH else Phase.SOUTH

    def _start_transition(self, desired_phase: str, reason: str) -> dict:
        self.next_phase       = desired_phase
        self.state            = State.YELLOW
        self.transition_timer = 0.0
        return self._result(f"{reason} -> Yellow")

    def _result(self, reason: str) -> dict:
        if self.state == State.YELLOW:
            sig_key = "SOUTH_YELLOW" if self.current_phase == Phase.SOUTH else "WEST_YELLOW"
        elif self.state == State.ALL_RED:
            sig_key = "ALL_RED"
        else:
            # IDLE и ACTIVE — зелёный текущей фазы
            sig_key = "SOUTH_GREEN" if self.current_phase == Phase.SOUTH else "WEST_GREEN"

        return {
            "signal": SIGNAL[sig_key],
            "state":  self.state,
            "reason": reason,
        }


# ── Запуск ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    sumo_cmd = [
        "sumo-gui",
        "-c", "Test1.sumocfg",
        "--step-length", str(SIM_STEP),
        "--delay", "100",
    ]

    traci.start(sumo_cmd)
    controller = AdaptiveController()

    print("── Строки сигналов ──────────────────────────────────")
    for k, v in SIGNAL.items():
        print(f"  {k:15} : {v}")
    print("─────────────────────────────────────────────────────")

    while traci.simulation.getMinExpectedNumber() > 0:
        traci.simulationStep()

        count_s = traci.lanearea.getLastStepVehicleNumber(DET_SOUTH)
        count_w = traci.lanearea.getLastStepVehicleNumber(DET_WEST)

        result = controller.step(count_s, count_w)
        traci.trafficlight.setRedYellowGreenState(TLS_ID, result["signal"])

        t = traci.simulation.getTime()
        if abs(t - round(t)) < SIM_STEP / 2:
            print(
                f"t={t:6.1f}s | {result['state']:8} | "
                f"sig={result['signal']} | "
                f"S={count_s} W={count_w} | "
                f"{result['reason']}"
            )

    traci.close()