"""
Fuzzy controller khusus SUMO/TraCI yang memakai baseline dari database.
"""

from typing import Dict, Tuple

import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl

MIN_GREEN = 10
MAX_GREEN = 60


class DBCalibratedFuzzyController:
    """
    Input:
    - demand share terhadap fase aktif
    - peak queue pada pendekat terpadat dalam fase aktif
    - peak mode (off-peak vs peak)

    Output:
    - bias detik terhadap baseline green dari database
    """

    def __init__(self):
        self._build()

    def _build(self):
        self.share_delta = ctrl.Antecedent(np.arange(-12, 13, 1), "share_delta")
        self.phase_peak = ctrl.Antecedent(np.arange(0, 31, 1), "phase_peak")
        self.peak_mode = ctrl.Antecedent(np.arange(0, 11, 1), "peak_mode")
        self.green_bias = ctrl.Consequent(np.arange(-6, 7, 1), "green_bias")

        self.share_delta["Deficit"] = fuzz.trapmf(self.share_delta.universe, [-12, -12, -6, -1])
        self.share_delta["Balanced"] = fuzz.trimf(self.share_delta.universe, [-3, 0, 3])
        self.share_delta["Dominant"] = fuzz.trapmf(self.share_delta.universe, [1, 6, 12, 12])

        self.phase_peak["Low"] = fuzz.trapmf(self.phase_peak.universe, [0, 0, 4, 8])
        self.phase_peak["Medium"] = fuzz.trimf(self.phase_peak.universe, [5, 10, 15])
        self.phase_peak["High"] = fuzz.trapmf(self.phase_peak.universe, [12, 18, 30, 30])

        self.peak_mode["OffPeak"] = fuzz.trapmf(self.peak_mode.universe, [0, 0, 2, 4])
        self.peak_mode["Peak"] = fuzz.trapmf(self.peak_mode.universe, [6, 8, 10, 10])

        self.green_bias["ShortenStrong"] = fuzz.trapmf(self.green_bias.universe, [-6, -6, -4, -2])
        self.green_bias["ShortenSlight"] = fuzz.trimf(self.green_bias.universe, [-3, -1, 0])
        self.green_bias["Keep"] = fuzz.trimf(self.green_bias.universe, [-1, 0, 1])
        self.green_bias["ExtendSlight"] = fuzz.trimf(self.green_bias.universe, [0, 1, 3])
        self.green_bias["ExtendStrong"] = fuzz.trapmf(self.green_bias.universe, [2, 4, 6, 6])
        self.green_bias.defuzzify_method = "centroid"

        rules = [
            ctrl.Rule(self.share_delta["Balanced"] & self.phase_peak["Low"], self.green_bias["Keep"]),
            ctrl.Rule(self.share_delta["Balanced"] & self.phase_peak["Medium"], self.green_bias["Keep"]),
            ctrl.Rule(
                self.share_delta["Balanced"] & self.phase_peak["High"] & self.peak_mode["OffPeak"],
                self.green_bias["Keep"],
            ),
            ctrl.Rule(
                self.share_delta["Balanced"] & self.phase_peak["High"] & self.peak_mode["Peak"],
                self.green_bias["ExtendSlight"],
            ),
            ctrl.Rule(self.share_delta["Dominant"] & self.phase_peak["Low"], self.green_bias["ExtendSlight"]),
            ctrl.Rule(self.share_delta["Dominant"] & self.phase_peak["Medium"], self.green_bias["ExtendSlight"]),
            ctrl.Rule(
                self.share_delta["Dominant"] & self.phase_peak["High"] & self.peak_mode["OffPeak"],
                self.green_bias["ExtendSlight"],
            ),
            ctrl.Rule(
                self.share_delta["Dominant"] & self.phase_peak["High"] & self.peak_mode["Peak"],
                self.green_bias["ExtendStrong"],
            ),
            ctrl.Rule(self.share_delta["Deficit"] & self.phase_peak["Low"], self.green_bias["ShortenSlight"]),
            ctrl.Rule(self.share_delta["Deficit"] & self.phase_peak["Medium"], self.green_bias["ShortenStrong"]),
            ctrl.Rule(self.share_delta["Deficit"] & self.phase_peak["High"], self.green_bias["ShortenStrong"]),
        ]
        self._sim = ctrl.ControlSystemSimulation(ctrl.ControlSystem(rules))

    def infer(
        self,
        *,
        baseline_green: int,
        demand_share: float,
        phase_peak_queue: float,
        peak_mode: bool,
    ) -> Tuple[int, Dict]:
        share_delta = int(round(max(-12.0, min(12.0, (float(demand_share) - 0.5) * 100.0))))
        peak_queue = int(round(max(0.0, min(30.0, float(phase_peak_queue)))))
        peak_flag = 10 if peak_mode else 0

        try:
            self._sim.input["share_delta"] = share_delta
            self._sim.input["phase_peak"] = peak_queue
            self._sim.input["peak_mode"] = peak_flag
            self._sim.compute()
            bias = int(round(float(self._sim.output["green_bias"])))
        except Exception:
            bias = 0

        if peak_mode:
            bias = max(-4, min(5, bias))
        else:
            bias = max(-3, min(3, bias))

        duration = int(round(int(baseline_green) + bias))
        duration = max(MIN_GREEN, min(MAX_GREEN, duration))
        return duration, {
            "baseline_green": int(baseline_green),
            "demand_share": round(float(demand_share), 4),
            "share_delta": share_delta,
            "phase_peak_queue": peak_queue,
            "peak_mode": bool(peak_mode),
            "bias_s": bias,
            "durasi": duration,
        }
