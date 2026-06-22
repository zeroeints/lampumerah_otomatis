"""
Modul logika fuzzy dasar untuk durasi lampu hijau.
Dipertahankan untuk kompatibilitas modul lama.
"""

from typing import Dict, Tuple

import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl

MIN_GREEN = 10
MAX_GREEN = 60
DEFAULT = 30


class FuzzyTrafficController:
    """
    Input: kepadatan kendaraan 0-30
    Output: durasi hijau 10-60 detik
    """

    def __init__(self):
        self._build()

    def _build(self):
        self.n_kend = ctrl.Antecedent(np.arange(0, 31, 1), "kendaraan")
        self.t_hijau = ctrl.Consequent(np.arange(MIN_GREEN, MAX_GREEN + 1, 1), "durasi")

        self.n_kend["Sedikit"] = fuzz.trapmf(self.n_kend.universe, [0, 0, 5, 11])
        self.n_kend["Sedang"] = fuzz.trimf(self.n_kend.universe, [5, 11, 18])
        self.n_kend["Padat"] = fuzz.trapmf(self.n_kend.universe, [13, 18, 30, 30])

        self.t_hijau["Pendek"] = fuzz.trapmf(self.t_hijau.universe, [10, 10, 17, 24])
        self.t_hijau["Sedang"] = fuzz.trimf(self.t_hijau.universe, [19, 29, 39])
        self.t_hijau["Panjang"] = fuzz.trapmf(self.t_hijau.universe, [35, 46, 60, 60])
        self.t_hijau.defuzzify_method = "centroid"

        rules = [
            ctrl.Rule(self.n_kend["Sedikit"], self.t_hijau["Pendek"]),
            ctrl.Rule(self.n_kend["Sedang"], self.t_hijau["Sedang"]),
            ctrl.Rule(self.n_kend["Padat"], self.t_hijau["Panjang"]),
        ]
        self._sim = ctrl.ControlSystemSimulation(ctrl.ControlSystem(rules))

    def fuzzify(self, n: int) -> Dict[str, float]:
        n = max(0, min(30, n))
        u = self.n_kend.universe
        return {
            "Sedikit": round(float(fuzz.interp_membership(u, self.n_kend["Sedikit"].mf, n)), 4),
            "Sedang": round(float(fuzz.interp_membership(u, self.n_kend["Sedang"].mf, n)), 4),
            "Padat": round(float(fuzz.interp_membership(u, self.n_kend["Padat"].mf, n)), 4),
        }

    def infer(self, vehicle_count: int) -> Tuple[int, Dict]:
        n = max(0, min(30, int(vehicle_count)))
        try:
            self._sim.input["kendaraan"] = n
            self._sim.compute()
            out = int(round(float(self._sim.output["durasi"])))
            out = max(MIN_GREEN, min(MAX_GREEN, out))
        except Exception:
            out = DEFAULT

        mf = self.fuzzify(n)
        label = max(mf, key=mf.get)
        return out, {
            "input": n,
            "label": label,
            "mu": mf,
            "durasi": out,
            "rule": f"IF Kepadatan={label} THEN Durasi={out}s",
        }

    def decide_ns_ew(self, ns_total: int, ew_total: int) -> Dict:
        ns_dur, ns_det = self.infer(ns_total // 2)
        ew_dur, ew_det = self.infer(ew_total // 2)
        return {
            "NS": ns_dur,
            "EW": ew_dur,
            "NS_detail": ns_det,
            "EW_detail": ew_det,
        }

    def get_membership_curves(self) -> Dict:
        return {
            "universe": self.n_kend.universe.tolist(),
            "input": {
                "Sedikit": self.n_kend["Sedikit"].mf.tolist(),
                "Sedang": self.n_kend["Sedang"].mf.tolist(),
                "Padat": self.n_kend["Padat"].mf.tolist(),
            },
            "out_universe": self.t_hijau.universe.tolist(),
            "output": {
                "Pendek": self.t_hijau["Pendek"].mf.tolist(),
                "Sedang": self.t_hijau["Sedang"].mf.tolist(),
                "Panjang": self.t_hijau["Panjang"].mf.tolist(),
            },
        }
