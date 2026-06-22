"""
fuzzy_controller_opt.py — Versi OPTIMASI dari fuzzy_controller.py
=============================================================================
Perubahan dari versi asli:
  1. Ditambahkan INPUT KEDUA: panjang antrean (0-50) — sebelumnya hanya 1 input
  2. Jumlah rules ditambah dari 3 menjadi 9 (grid 3x3)
  3. MF Input disesuaikan: overlap lebih banyak di zona transisi kritis
  4. MF Output digeser ke atas: "Sedang" bercentroid ~34s (> Fixed 30s)

Cara mengembalikan ke versi asli:
  Di sumo_simulation_opt.py, ganti:
    from fuzzy.fuzzy_controller_opt import FuzzyTrafficController
  menjadi:
    from fuzzy.fuzzy_controller import FuzzyTrafficController
=============================================================================
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
    Versi optimasi dengan 2 input:
      - Input 1: kepadatan kendaraan (0-30)
      - Input 2: panjang antrean (0-50)
      - Output : durasi hijau (10-60 detik)

    9 aturan fuzzy (3x3 grid) untuk keputusan yang lebih cerdas.
    """

    def __init__(self):
        self._build()

    def _build(self):
        # ── INPUT 1: Kepadatan Kendaraan (0-30) ──────────────
        # Temuan #7: Overlap diperluas di zona transisi kritis
        self.n_kend = ctrl.Antecedent(np.arange(0, 31, 1), "kendaraan")
        self.n_kend["Sedikit"] = fuzz.trapmf(self.n_kend.universe, [0, 0, 4, 10])
        self.n_kend["Sedang"]  = fuzz.trimf(self.n_kend.universe, [6, 13, 22])
        self.n_kend["Padat"]   = fuzz.trapmf(self.n_kend.universe, [16, 22, 30, 30])

        # ── INPUT 2: Panjang Antrean (0-50) ──────────────────
        # Temuan #1: Input kedua agar Fuzzy lebih cerdas
        self.n_antr = ctrl.Antecedent(np.arange(0, 51, 1), "antrean")
        self.n_antr["Pendek"]  = fuzz.trapmf(self.n_antr.universe, [0, 0, 5, 15])
        self.n_antr["Sedang"]  = fuzz.trimf(self.n_antr.universe, [10, 20, 35])
        self.n_antr["Panjang"] = fuzz.trapmf(self.n_antr.universe, [25, 35, 50, 50])

        # ── OUTPUT: Durasi Hijau (10-60 detik) ───────────────
        # Temuan #6: Centroid "Sedang" digeser ke ~34s (> Fixed 30s)
        self.t_hijau = ctrl.Consequent(np.arange(MIN_GREEN, MAX_GREEN + 1, 1), "durasi")
        self.t_hijau["Pendek"]  = fuzz.trapmf(self.t_hijau.universe, [10, 10, 20, 28])
        self.t_hijau["Sedang"]  = fuzz.trimf(self.t_hijau.universe, [22, 34, 46])
        self.t_hijau["Panjang"] = fuzz.trapmf(self.t_hijau.universe, [38, 48, 60, 60])
        self.t_hijau.defuzzify_method = "centroid"

        # ── 9 RULES (3x3 Grid) ──────────────────────────────
        # Temuan #1: Jumlah rules ditambah dari 3 menjadi 9
        rules = [
            # Kendaraan Sedikit
            ctrl.Rule(self.n_kend["Sedikit"] & self.n_antr["Pendek"],  self.t_hijau["Pendek"]),
            ctrl.Rule(self.n_kend["Sedikit"] & self.n_antr["Sedang"],  self.t_hijau["Pendek"]),
            ctrl.Rule(self.n_kend["Sedikit"] & self.n_antr["Panjang"], self.t_hijau["Sedang"]),
            # Kendaraan Sedang
            ctrl.Rule(self.n_kend["Sedang"]  & self.n_antr["Pendek"],  self.t_hijau["Pendek"]),
            ctrl.Rule(self.n_kend["Sedang"]  & self.n_antr["Sedang"],  self.t_hijau["Sedang"]),
            ctrl.Rule(self.n_kend["Sedang"]  & self.n_antr["Panjang"], self.t_hijau["Panjang"]),
            # Kendaraan Padat
            ctrl.Rule(self.n_kend["Padat"]   & self.n_antr["Pendek"],  self.t_hijau["Sedang"]),
            ctrl.Rule(self.n_kend["Padat"]   & self.n_antr["Sedang"],  self.t_hijau["Panjang"]),
            ctrl.Rule(self.n_kend["Padat"]   & self.n_antr["Panjang"], self.t_hijau["Panjang"]),
        ]
        self._sim = ctrl.ControlSystemSimulation(ctrl.ControlSystem(rules))

    def fuzzify(self, n: int) -> Dict[str, float]:
        """Fuzzifikasi input kepadatan kendaraan."""
        n = max(0, min(30, n))
        u = self.n_kend.universe
        return {
            "Sedikit": round(float(fuzz.interp_membership(u, self.n_kend["Sedikit"].mf, n)), 4),
            "Sedang":  round(float(fuzz.interp_membership(u, self.n_kend["Sedang"].mf, n)), 4),
            "Padat":   round(float(fuzz.interp_membership(u, self.n_kend["Padat"].mf, n)), 4),
        }

    def fuzzify_queue(self, q: int) -> Dict[str, float]:
        """Fuzzifikasi input panjang antrean."""
        q = max(0, min(50, q))
        u = self.n_antr.universe
        return {
            "Pendek":  round(float(fuzz.interp_membership(u, self.n_antr["Pendek"].mf, q)), 4),
            "Sedang":  round(float(fuzz.interp_membership(u, self.n_antr["Sedang"].mf, q)), 4),
            "Panjang": round(float(fuzz.interp_membership(u, self.n_antr["Panjang"].mf, q)), 4),
        }

    def infer(self, vehicle_count: int, queue_length: int = 0) -> Tuple[int, Dict]:
        """
        Inferensi Fuzzy dengan 2 input.

        Parameters:
            vehicle_count: jumlah kendaraan (0-30)
            queue_length:  panjang antrean (0-50), default=0 untuk backward compatibility
        """
        n = max(0, min(30, int(vehicle_count)))
        q = max(0, min(50, int(queue_length)))
        try:
            self._sim.input["kendaraan"] = n
            self._sim.input["antrean"] = q
            self._sim.compute()
            out = int(round(float(self._sim.output["durasi"])))
            out = max(MIN_GREEN, min(MAX_GREEN, out))
        except Exception:
            out = DEFAULT

        mf_kend = self.fuzzify(n)
        mf_antr = self.fuzzify_queue(q)
        label_kend = max(mf_kend, key=mf_kend.get)
        label_antr = max(mf_antr, key=mf_antr.get)
        return out, {
            "input_kendaraan": n,
            "input_antrean": q,
            "label_kendaraan": label_kend,
            "label_antrean": label_antr,
            "mu_kendaraan": mf_kend,
            "mu_antrean": mf_antr,
            "durasi": out,
            "rule": f"IF Kepadatan={label_kend} AND Antrean={label_antr} THEN Durasi={out}s",
        }

    def decide_ns_ew(self, ns_total: int, ew_total: int) -> Dict:
        """Backward-compatible: keputusan NS vs EW."""
        ns_dur, ns_det = self.infer(ns_total // 2)
        ew_dur, ew_det = self.infer(ew_total // 2)
        return {
            "NS": ns_dur,
            "EW": ew_dur,
            "NS_detail": ns_det,
            "EW_detail": ew_det,
        }

    def get_membership_curves(self) -> Dict:
        """Kembalikan kurva MF untuk visualisasi."""
        return {
            "universe": self.n_kend.universe.tolist(),
            "input": {
                "Sedikit": self.n_kend["Sedikit"].mf.tolist(),
                "Sedang":  self.n_kend["Sedang"].mf.tolist(),
                "Padat":   self.n_kend["Padat"].mf.tolist(),
            },
            "queue_universe": self.n_antr.universe.tolist(),
            "input_queue": {
                "Pendek":  self.n_antr["Pendek"].mf.tolist(),
                "Sedang":  self.n_antr["Sedang"].mf.tolist(),
                "Panjang": self.n_antr["Panjang"].mf.tolist(),
            },
            "out_universe": self.t_hijau.universe.tolist(),
            "output": {
                "Pendek":  self.t_hijau["Pendek"].mf.tolist(),
                "Sedang":  self.t_hijau["Sedang"].mf.tolist(),
                "Panjang": self.t_hijau["Panjang"].mf.tolist(),
            },
        }
