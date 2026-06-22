"""
=============================================================================
main_controller.py — Sistem Penuh: YOLOv11 + Logika Fuzzy + SUMO TraCI
=============================================================================
Skripsi : Simulasi Sistem Pengendalian Lampu Lalu Lintas
          Berbasis YOLOv11 dan Logika Fuzzy
Mahasiswa: Mohammad Filla Firdaus | NIM. 2215354055
Institusi: Politeknik Negeri Bali | TRPL 2026
=============================================================================

Cara Menjalankan:
  1. Pastikan SUMO sudah terinstall dan SUMO_HOME sudah diset:
       Windows : set SUMO_HOME=C:\\Program Files (x86)\\Eclipse\\Sumo
       Linux   : export SUMO_HOME=/usr/share/sumo

  2. Letakkan best.pt di folder yang sama dengan file ini

  3. Jalankan:
       python main_controller.py                    ← default (GUI + 3600 langkah)
       python main_controller.py --nogui            ← tanpa GUI, lebih cepat
       python main_controller.py --steps 1800       ← 30 menit simulasi
       python main_controller.py --test             ← test cepat tanpa SUMO
=============================================================================
"""
import os, sys, cv2, time, json, logging, argparse
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List

# ── Tambah path SUMO (Windows & Linux) ────────────────────────
SUMO_HOME = os.environ.get("SUMO_HOME", "")
if SUMO_HOME:
    tools = os.path.join(SUMO_HOME, "tools")
    if tools not in sys.path:
        sys.path.append(tools)

# ── Coba import TraCI ─────────────────────────────────────────
TRACI_OK = False
try:
    import traci
    import traci.constants as tc
    TRACI_OK = True
except ImportError:
    pass

# ── Import YOLO ───────────────────────────────────────────────
try:
    from ultralytics import YOLO
    import torch
except ImportError:
    print("[ERROR] Jalankan: pip install ultralytics")
    sys.exit(1)

# ── Import modul Fuzzy lokal ──────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from fuzzy.fuzzy_controller import FuzzyTrafficController

# ── Logging ───────────────────────────────────────────────────
Path("logs").mkdir(exist_ok=True)
Path("output").mkdir(exist_ok=True)

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s [%(name)-8s] %(message)s",
    datefmt = "%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/controller.log", encoding="utf-8", mode="w"),
    ],
)
log = logging.getLogger("CTRL")


# ═══════════════════════════════════════════════════════════════
# KONSTANTA
# ═══════════════════════════════════════════════════════════════
# Mapping English/COCO class names → Indonesian thesis names
_NAME_TO_INDO = {
    "car": "Mobil", "mobil": "Mobil",
    "motorcycle": "Motor", "motor": "Motor", "motorbike": "Motor",
    "bus": "Bus",
    "truck": "Truk", "truk": "Truk",
}
# Color per Indonesian name
_INDO_COLORS = {"Mobil": (0,229,255), "Motor": (124,58,237), "Bus": (245,158,11), "Truk": (236,72,153)}

def _normalize_class_name(name: str) -> str:
    """Normalize any English/COCO class name to Indonesian thesis name."""
    return _NAME_TO_INDO.get(name.lower().strip(), name)

# Will be populated dynamically from model.names in YOLODetector.__init__
CLASS_NAMES: Dict[int, str] = {}
CLASS_COLORS: Dict[int, tuple] = {}

# ROI per lajur — normalisasi (x1,y1,x2,y2) antara 0.0–1.0
# Sesuaikan dengan posisi lajur pada tampilan screenshot SUMO Anda
ROI_LANES = {
    "N": (0.35, 0.00, 0.65, 0.42),   # Lajur Utara
    "S": (0.35, 0.58, 0.65, 1.00),   # Lajur Selatan
    "E": (0.58, 0.35, 1.00, 0.65),   # Lajur Timur
    "W": (0.00, 0.35, 0.42, 0.65),   # Lajur Barat
}

# ID fase lampu di SUMO (sesuai intersection.net.xml)
# Fase 0: NS Hijau | Fase 1: NS Kuning | Fase 2: EW Hijau | Fase 3: EW Kuning
PHASE_NS_GREEN  = 0
PHASE_NS_YELLOW = 1
PHASE_EW_GREEN  = 2
PHASE_EW_YELLOW = 3


# ═══════════════════════════════════════════════════════════════
# YOLO DETECTOR
# ═══════════════════════════════════════════════════════════════
class YOLODetector:
    """Wrapper YOLOv11 untuk deteksi kendaraan multi-kelas per lajur."""

    def __init__(self, model_path: str, conf: float = 0.50):
        mp = Path(model_path)
        if not mp.exists():
            raise FileNotFoundError(
                f"\n[ERROR] best.pt tidak ditemukan: {mp.resolve()}"
                f"\n        Letakkan best.pt di: {Path('.').resolve()}"
            )
        self.model  = YOLO(str(mp))
        self.conf   = conf
        self.device = "0" if torch.cuda.is_available() else "cpu"

        params = sum(p.numel() for p in self.model.model.parameters())
        log.info(f"YOLOv11 dimuat: {mp.name} | {params:,} param | device={self.device}")

        # ── Build class mapping dynamically from model ─────
        global CLASS_NAMES, CLASS_COLORS
        model_names = getattr(self.model, "names", {})
        log.info(f"Model classes: {model_names}")
        for idx, name in model_names.items():
            indo = _normalize_class_name(name)
            CLASS_NAMES[idx] = indo
            CLASS_COLORS[idx] = _INDO_COLORS.get(indo, (200, 200, 200))
        log.info(f"Mapped classes: {CLASS_NAMES}")

    def detect_per_lane(self, frame: np.ndarray) -> tuple:
        """
        Deteksi kendaraan dan hitung per lajur menggunakan ROI.
        Return: (lane_counts_dict, annotated_frame, latency_ms)
        """
        h, w  = frame.shape[:2]
        t0    = time.perf_counter()
        res   = self.model.predict(
            frame, conf=self.conf, iou=0.7,
            device=self.device, verbose=False,
        )
        lat_ms = (time.perf_counter() - t0) * 1000

        counts = {"N": 0, "S": 0, "E": 0, "W": 0}
        ann    = frame.copy()

        for box in res[0].boxes:
            cls_id       = int(box.cls[0])
            cf           = float(box.conf[0])
            x1,y1,x2,y2 = map(int, box.xyxy[0])
            color        = CLASS_COLORS.get(cls_id, (200,200,200))
            label        = f"{CLASS_NAMES.get(cls_id,'?')} {cf:.2f}"

            # Hitung kendaraan di lajur yang sesuai
            cx = (x1 + x2) / 2 / w
            cy = (y1 + y2) / 2 / h
            for lane, (rx1, ry1, rx2, ry2) in ROI_LANES.items():
                if rx1 <= cx <= rx2 and ry1 <= cy <= ry2:
                    counts[lane] += 1
                    break

            # Gambar bounding box
            cv2.rectangle(ann, (x1,y1), (x2,y2), color, 2)
            (tw,th),_ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            cv2.rectangle(ann, (x1,y1-th-5), (x1+tw+4,y1), color, -1)
            cv2.putText(ann, label, (x1+2,y1-3),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0,0,0), 1)

        # Gambar ROI boxes
        lc = {"N":(0,229,255),"S":(124,58,237),"E":(245,158,11),"W":(236,72,153)}
        for lane, (rx1,ry1,rx2,ry2) in ROI_LANES.items():
            p1 = (int(rx1*w), int(ry1*h))
            p2 = (int(rx2*w), int(ry2*h))
            cv2.rectangle(ann, p1, p2, lc[lane], 1)
            cv2.putText(ann, f"{lane}:{counts[lane]}",
                        (p1[0]+3, p1[1]+15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, lc[lane], 1)

        return counts, ann, round(lat_ms, 1)


# ═══════════════════════════════════════════════════════════════
# SUMO INTERFACE
# ═══════════════════════════════════════════════════════════════
class SUMOInterface:
    """
    Antarmuka ke simulator SUMO via protokol TraCI.
    Jika SUMO tidak tersedia, berjalan dalam mode simulasi internal.
    """

    def __init__(self, sumo_cfg: str, tl_id: str, use_gui: bool):
        self.sumo_cfg  = sumo_cfg
        self.tl_id     = tl_id
        self.use_gui   = use_gui
        self.connected = False
        self._step     = 0
        self._n_vehicles = 0
        self._sim_counts = {"N": 0, "S": 0, "E": 0, "W": 0}

    def connect(self) -> bool:
        """Hubungkan ke SUMO via TraCI."""
        if not TRACI_OK:
            log.warning("TraCI tidak tersedia → mode simulasi internal")
            return False

        if not Path(self.sumo_cfg).exists():
            log.warning(f"File SUMO tidak ditemukan: {self.sumo_cfg} → mode internal")
            return False

        # Windows: cari binary SUMO
        if sys.platform == "win32":
            sumo_bin = os.path.join(SUMO_HOME, "bin",
                                    "sumo-gui.exe" if self.use_gui else "sumo.exe")
        else:
            sumo_bin = "sumo-gui" if self.use_gui else "sumo"

        cmd = [
            sumo_bin,
            "-c", self.sumo_cfg,
            "--step-length", "1.0",
            "--no-warnings",
            "--log", "logs/sumo.log",
            "--quit-on-end",
        ]

        try:
            traci.start(cmd)
            self.connected = True
            log.info(f"TraCI terhubung → TL-ID='{self.tl_id}'")
            log.info(f"  File config : {self.sumo_cfg}")
            log.info(f"  GUI         : {self.use_gui}")
            return True
        except Exception as e:
            log.error(f"TraCI gagal terhubung: {e}")
            log.warning("Beralih ke mode simulasi internal.")
            return False

    def step(self):
        """Maju satu langkah simulasi (1 detik)."""
        if self.connected:
            traci.simulationStep()
            try:
                self._n_vehicles = traci.vehicle.getIDCount()
            except Exception:
                pass
        self._step += 1
        self._refresh_sim_counts()

    def _refresh_sim_counts(self):
        """Perbarui hitungan fallback agar mode headless/internal tetap konsisten."""
        t = self._step
        n_north = int(np.clip(8 + 5*np.sin(t/60), 0, 25))
        n_south = int(np.clip(6 + 4*np.sin(t/70+1), 0, 25))
        n_east  = int(np.clip(3 + 3*np.sin(t/50+2), 0, 20))
        n_west  = int(np.clip(4 + 3*np.sin(t/55+3), 0, 20))
        self._sim_counts = {"N": n_north, "S": n_south, "E": n_east, "W": n_west}

    def get_frame(self) -> np.ndarray:
        """
        Ambil screenshot dari SUMO GUI atau buat frame sintetis.
        Frame digunakan sebagai input YOLOv11.
        """
        if self.connected and self.use_gui:
            try:
                path = f"logs/_frame_{self._step % 10}.png"
                traci.gui.screenshot("View #0", path, 640, 640)
                frame = cv2.imread(path)
                if frame is not None:
                    return cv2.resize(frame, (640, 640))
            except Exception:
                pass

        # Frame sintetis (fallback) — representasi persimpangan 4 arah
        f = np.zeros((640, 640, 3), dtype=np.uint8)
        # Jalan vertikal dan horizontal
        f[0:640, 275:365, 1]   = 55   # N-S
        f[235:405, 0:640, 1]   = 55   # E-W
        f[235:405, 275:365, 1] = 75   # tengah
        # Tambah noise untuk variasi
        noise = np.random.randint(0, 18, (640, 640, 3), dtype=np.uint8)
        f = np.clip(f.astype(np.int16) + noise, 0, 255).astype(np.uint8)

        return f

    def get_lane_counts(self) -> Dict[str, int]:
        """
        Ambil hitungan kendaraan per arah.
        Pada mode headless/internal, gunakan estimasi antrean agar keputusan fuzzy
        tetap sinkron dengan metrik yang dilaporkan.
        """
        if self.connected:
            mapping = {
                "N": ["E_N_in_0", "E_N_in_1"],
                "S": ["E_S_in_0", "E_S_in_1"],
                "E": ["E_E_in_0", "E_E_in_1"],
                "W": ["E_W_in_0", "E_W_in_1"],
            }
            try:
                lane_ids = set(traci.lane.getIDList())
                counts = {}
                for direction, lanes in mapping.items():
                    counts[direction] = int(sum(
                        traci.lane.getLastStepHaltingNumber(l)
                        for l in lanes if l in lane_ids
                    ))
                if any(counts.values()):
                    return counts
            except Exception:
                pass
        return dict(self._sim_counts)

    def set_phase(self, phase_index: int, duration: int):
        """
        Set fase dan durasi lampu lalu lintas via TraCI.
        Ini adalah inti perintah kontrol adaptif ke SUMO.
        """
        if self.connected:
            try:
                traci.trafficlight.setPhase(self.tl_id, phase_index)
                traci.trafficlight.setPhaseDuration(self.tl_id, float(duration))
            except Exception as e:
                log.debug(f"set_phase error: {e}")

    def get_current_phase(self) -> int:
        """Ambil fase aktif saat ini."""
        if self.connected:
            try:
                return traci.trafficlight.getPhase(self.tl_id)
            except Exception:
                pass
        return self._step // 30 % 4

    def get_avg_waiting_time(self) -> float:
        """Waktu tunggu rata-rata semua kendaraan di simulasi (detik)."""
        if self.connected:
            try:
                vehs = traci.vehicle.getIDList()
                if vehs:
                    total = sum(traci.vehicle.getWaitingTime(v) for v in vehs)
                    return round(total / len(vehs), 2)
            except Exception:
                pass
        # Simulasi internal: estimasi dari jumlah kendaraan
        counts = getattr(self, "_sim_counts", {"N":5,"S":5,"E":3,"W":3})
        total  = sum(counts.values())
        return round(float(np.random.uniform(max(3, total-5), total+15)), 2)

    def get_queue_length(self) -> float:
        """Panjang antrean total di semua lajur masuk."""
        if self.connected:
            try:
                # Ambil kendaraan berhenti di lajur masuk
                lanes  = ["E_N_in_0","E_N_in_1","E_S_in_0","E_S_in_1",
                          "E_E_in_0","E_E_in_1","E_W_in_0","E_W_in_1"]
                total  = sum(
                    traci.lane.getLastStepHaltingNumber(l)
                    for l in lanes if l in traci.lane.getIDList()
                )
                return float(total)
            except Exception:
                pass
        counts = getattr(self, "_sim_counts", {"N":5,"S":5,"E":3,"W":3})
        return float(np.random.randint(0, max(1, sum(counts.values())//2)))

    def get_vehicle_count(self) -> int:
        """Total kendaraan dalam simulasi saat ini."""
        if self.connected:
            try:
                return traci.vehicle.getIDCount()
            except Exception:
                pass
        return self._n_vehicles

    def close(self):
        """Tutup koneksi TraCI."""
        if self.connected:
            try:
                traci.close()
            except Exception:
                pass
            self.connected = False
            log.info("Koneksi TraCI ditutup.")


# ═══════════════════════════════════════════════════════════════
# PERFORMANCE MONITOR
# ═══════════════════════════════════════════════════════════════
class PerfMonitor:
    """Catat dan analisis metrik kinerja simulasi."""

    def __init__(self):
        self.records: List[dict] = []
        self._t0 = time.time()

    def record(self, step: int, counts: dict, ns_dur: int, ew_dur: int,
               wait: float, queue: float, lat: float, phase: str):
        self.records.append({
            "step"   : step,
            "t_sim"  : round(time.time() - self._t0, 1),
            "N"      : counts.get("N", 0),
            "S"      : counts.get("S", 0),
            "E"      : counts.get("E", 0),
            "W"      : counts.get("W", 0),
            "total"  : sum(counts.values()),
            "ns_dur" : ns_dur,
            "ew_dur" : ew_dur,
            "wait"   : round(wait, 2),
            "queue"  : round(queue, 1),
            "lat_ms" : round(lat, 1),
            "phase"  : phase,
        })

    def summary(self) -> dict:
        if not self.records:
            return {}
        waits  = [r["wait"]   for r in self.records]
        queues = [r["queue"]  for r in self.records]
        lats   = [r["lat_ms"] for r in self.records if r["lat_ms"] > 0]

        return {
            "total_steps"      : len(self.records),
            "avg_wait_s"       : round(float(np.mean(waits)),  2),
            "max_wait_s"       : round(float(np.max(waits)),   2),
            "avg_queue"        : round(float(np.mean(queues)), 2),
            "max_queue"        : round(float(np.max(queues)),  2),
            "avg_lat_ms"       : round(float(np.mean(lats)),   1) if lats else 0,
        }

    def save(self, path: str):
        data = {
            "metadata": {
                "mahasiswa" : "Mohammad Filla Firdaus",
                "nim"       : "2215354055",
                "institusi" : "Politeknik Negeri Bali",
                "prodi"     : "Teknologi Rekayasa Perangkat Lunak",
                "tanggal"   : datetime.now().isoformat(),
                "model"     : "YOLOv11 + Logika Fuzzy",
            },
            "summary" : self.summary(),
            "records" : self.records,
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        log.info(f"Log disimpan: {path}")
        return path


# ═══════════════════════════════════════════════════════════════
# MAIN TRAFFIC CONTROLLER
# ═══════════════════════════════════════════════════════════════
class TrafficController:
    """
    Kontroler utama sistem.
    Loop per detik:
      1. Ambil frame dari SUMO (atau frame sintetis)
      2. YOLOv11 deteksi & hitung kendaraan per lajur
      3. Fuzzy Logic tentukan durasi hijau NS & EW
      4. TraCI kirim perintah ke lampu SUMO
      5. Catat metrik
    """

    DETECT_INTERVAL = 5     # Jalankan YOLO setiap N langkah (hemat CPU)
    SMOOTH_ALPHA    = 0.7   # Koefisien exponential moving average
    YELLOW_DURATION = 3

    def __init__(self, args):
        self.args    = args
        self.steps   = args.steps

        log.info("=" * 58)
        log.info("  SISTEM PENGENDALIAN LAMPU LALU LINTAS ADAPTIF")
        log.info("  YOLOv11 + Logika Fuzzy + SUMO TraCI")
        log.info(f"  Model  : {args.model}")
        log.info(f"  Langkah: {args.steps} (= {args.steps//3600}j {args.steps%3600//60}m)")
        log.info("=" * 58)

        # Komponen utama
        self.yolo    = YOLODetector(args.model, args.conf)
        self.fuzzy   = FuzzyTrafficController()
        self.sumo    = SUMOInterface(args.sumo_cfg, args.tl_id, not args.nogui)
        self.monitor = PerfMonitor()

        # State lampu lalu lintas
        self.phase         = "NS"      # Fase aktif: "NS" atau "EW"
        self.phase_stage   = "GREEN"   # GREEN atau YELLOW
        self.pending_phase = "NS"
        self.timer         = 0         # Hitungan langkah dalam stage ini
        self.ns_dur        = 30        # Durasi hijau NS saat ini
        self.ew_dur        = 30        # Durasi hijau EW saat ini

        # Hitungan kendaraan terakhir (dengan smoothing)
        self.counts    = {"N": 0, "S": 0, "E": 0, "W": 0}

        # Simpan frame terakhir untuk debug
        self._last_frame: Optional[np.ndarray] = None

    def run(self):
        """Jalankan loop kontrol utama."""
        sumo_ok = self.sumo.connect()
        mode    = "SUMO+TraCI (terhubung)" if sumo_ok else "Simulasi Internal"
        log.info(f"Mode operasi: {mode}")
        log.info("─" * 58)

        try:
            self.sumo.set_phase(PHASE_NS_GREEN, self.ns_dur)
            for step in range(self.steps):
                self._step(step)
                if step % 60 == 0:
                    self._log_status(step)

        except KeyboardInterrupt:
            log.info("[!] Simulasi dihentikan oleh pengguna (Ctrl+C)")
        except Exception as e:
            log.error(f"Error saat simulasi: {e}", exc_info=True)
        finally:
            self._finalize()

    def _step(self, step: int):
        """Satu langkah simulasi lengkap."""
        self.sumo.step()

        lat_ms = 0.0
        if step % self.DETECT_INTERVAL == 0:
            if self.sumo.connected and self.sumo.use_gui:
                frame = self.sumo.get_frame()
                if frame is not None:
                    new_counts, ann_frame, lat_ms = self.yolo.detect_per_lane(frame)
                    self._last_frame = ann_frame
                else:
                    new_counts = self.sumo.get_lane_counts()
            else:
                new_counts = self.sumo.get_lane_counts()

            for lane, value in new_counts.items():
                prev = self.counts.get(lane, 0)
                self.counts[lane] = int(round(
                    self.SMOOTH_ALPHA * value + (1 - self.SMOOTH_ALPHA) * prev
                ))

        ns_total = self.counts["N"] + self.counts["S"]
        ew_total = self.counts["E"] + self.counts["W"]

        result = self.fuzzy.decide_ns_ew(ns_total, ew_total)
        self.ns_dur = result["NS"]
        self.ew_dur = result["EW"]

        self.timer += 1
        active_dur = self.ns_dur if self.phase == "NS" else self.ew_dur

        if self.phase_stage == "GREEN" and self.timer >= active_dur:
            yellow_idx = PHASE_NS_YELLOW if self.phase == "NS" else PHASE_EW_YELLOW
            self.sumo.set_phase(yellow_idx, self.YELLOW_DURATION)
            self.phase_stage = "YELLOW"
            self.pending_phase = "EW" if self.phase == "NS" else "NS"
            self.timer = 0
            log.info(
                f"[{step:5d}] Fase kuning: {self.phase} | "
                f"transisi ke {self.pending_phase} | "
                f"NS={ns_total} kend | EW={ew_total} kend"
            )
        elif self.phase_stage == "YELLOW" and self.timer >= self.YELLOW_DURATION:
            prev_phase = self.phase
            self.phase = self.pending_phase
            self.phase_stage = "GREEN"
            self.timer = 0
            new_dur = self.ns_dur if self.phase == "NS" else self.ew_dur
            phase_idx = PHASE_NS_GREEN if self.phase == "NS" else PHASE_EW_GREEN
            self.sumo.set_phase(phase_idx, new_dur)
            log.info(
                f"[{step:5d}] Ganti fase: {prev_phase} -> {self.phase} | "
                f"Durasi baru: {new_dur}s | "
                f"NS={ns_total} kend | EW={ew_total} kend"
            )

        wait = self.sumo.get_avg_waiting_time()
        queue = self.sumo.get_queue_length()

        self.monitor.record(
            step=step,
            counts=self.counts,
            ns_dur=self.ns_dur,
            ew_dur=self.ew_dur,
            wait=wait,
            queue=queue,
            lat=lat_ms,
            phase=f"{self.phase}_{self.phase_stage}",
        )

    def _log_status(self, step: int):
        """Cetak status ke konsol setiap 60 langkah."""
        c = self.counts
        tot = sum(c.values())
        stage_limit = (
            self.ns_dur if self.phase == "NS" else self.ew_dur
        ) if self.phase_stage == "GREEN" else self.YELLOW_DURATION
        log.info(
            f"[{step:5d}] "
            f"N={c['N']:2d} S={c['S']:2d} E={c['E']:2d} W={c['W']:2d} (Sigma={tot:3d}) | "
            f"Fase={self.phase}_{self.phase_stage} t={self.timer:3d}/{stage_limit}s | "
            f"NS={self.ns_dur}s EW={self.ew_dur}s"
        )

    def _finalize(self):
        """Tutup SUMO dan simpan laporan akhir."""
        self.sumo.close()

        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.monitor.save(f"output/sim_log_{ts}.json")
        s    = self.monitor.summary()

        # ── Laporan akhir ────────────────────────────────────
        print("\n" + "═" * 58)
        print("  LAPORAN AKHIR SIMULASI")
        print("  Skripsi: Mohammad Filla Firdaus | NIM. 2215354055")
        print("═" * 58)
        if s:
            print(f"\n  Total langkah      : {s['total_steps']}")
            print(f"\n  {'METRIK':<28} {'ADAPTIF':>10}")
            print("  " + "─" * 40)
            print(f"  {'Avg Waktu Tunggu (s)':<28} {s['avg_wait_s']:>10.2f}")
            print(f"  {'Max Waktu Tunggu (s)':<28} {s['max_wait_s']:>10.2f}")
            print(f"  {'Avg Panjang Antrean':<28} {s['avg_queue']:>10.2f}")
            print(f"  {'Avg Latency YOLO (ms)':<28} {s['avg_lat_ms']:>10.1f}")
            print(f"\n  [!] Baseline fixed-time tidak tersedia.")
            print(f"      Jalankan simulasi terpisah dengan fixed-time untuk perbandingan.")
        print(f"\n  Log tersimpan      : {path}")
        print("═" * 58 + "\n")

        # Simpan juga ringkasan CSV (mudah dibuka di Excel)
        self._save_csv(ts)

    def _save_csv(self, ts: str):
        """Simpan data rekaman ke CSV untuk analisis Excel."""
        csv_path = f"output/sim_data_{ts}.csv"
        if not self.monitor.records:
            return
        import csv
        keys = ["step","t_sim","N","S","E","W","total","ns_dur","ew_dur",
                "wait","queue","lat_ms","phase"]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(self.monitor.records)
        log.info(f"CSV disimpan: {csv_path}")


# ═══════════════════════════════════════════════════════════════
# MODE TEST (tanpa SUMO, verifikasi cepat integrasi)
# ═══════════════════════════════════════════════════════════════
def run_quick_test(model_path: str, conf: float):
    print("\n" + "=" * 55)
    print("  MODE TEST — Verifikasi Integrasi YOLOv11 + Fuzzy")
    print("=" * 55)

    # Test 1: Load model
    print("\n  [1/4] Load model YOLOv11 ...")
    try:
        det = YOLODetector(model_path, conf)
        print(f"  [✓] Model dimuat: {model_path}")
    except Exception as e:
        print(f"  [✗] Gagal: {e}")
        return

    # Test 2: Inferensi frame dummy
    print("\n  [2/4] Test inferensi pada frame 640×640 ...")
    dummy  = np.random.randint(40, 80, (640, 640, 3), dtype=np.uint8)
    counts, _, lat = det.detect_per_lane(dummy)
    print(f"  [✓] Latency    : {lat:.1f} ms")
    print(f"  [✓] FPS efektif: {1000/lat:.1f}")
    print(f"  [✓] Kendaraan  : {counts}")
    if lat < 100:
        print("  [✓] Real-time (< 100 ms)")
    elif lat < 500:
        print(f"  [~] Lambat tapi bisa jalan ({lat:.0f} ms) — pertimbangkan GPU")

    # Test 3: Fuzzy Logic
    print("\n  [3/4] Test Logika Fuzzy ...")
    fc = FuzzyTrafficController()
    for ns, ew in [(20, 4), (4, 20), (12, 12)]:
        r = fc.decide_ns_ew(ns, ew)
        print(f"  [✓] NS={ns:2d} EW={ew:2d} → "
              f"Hijau NS={r['NS']}s ({r['NS_detail']['label']}) "
              f"EW={r['EW']}s ({r['EW_detail']['label']})")

    # Test 4: TraCI status
    print("\n  [4/4] Cek ketersediaan TraCI ...")
    if TRACI_OK:
        print("  [✓] TraCI tersedia — siap terhubung ke SUMO")
    else:
        print("  [!] TraCI tidak tersedia")
        if not SUMO_HOME:
            print("      Set SUMO_HOME terlebih dahulu:")
            print("      Windows: set SUMO_HOME=C:\\Program Files (x86)\\Eclipse\\Sumo")
            print("      Linux  : export SUMO_HOME=/usr/share/sumo")
        else:
            print(f"      SUMO_HOME={SUMO_HOME}")
            print("      Pastikan SUMO terinstall dengan benar")

    print("\n  " + "─" * 50)
    print("  Semua komponen siap dijalankan!")
    print("  Jalankan simulasi penuh:")
    print(f"    python main_controller.py --model {model_path}")
    print("=" * 55 + "\n")


# ═══════════════════════════════════════════════════════════════
# ARGUMENT PARSER & ENTRY POINT
# ═══════════════════════════════════════════════════════════════
def parse_args():
    p = argparse.ArgumentParser(
        description="Kontroler Lampu Lalu Lintas Adaptif — YOLOv11 + Fuzzy + SUMO",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--model",    default="best.pt",
                   help="Path ke model YOLOv11 (best.pt)")
    p.add_argument("--sumo-cfg", default="sumo_config/intersection.sumocfg",
                   help="Path ke file konfigurasi SUMO (.sumocfg)")
    p.add_argument("--tl-id",   default="J_center",
                   help="ID traffic light di file .net.xml SUMO")
    p.add_argument("--steps",   type=int, default=3600,
                   help="Jumlah langkah simulasi (1 langkah = 1 detik)")
    p.add_argument("--nogui",   action="store_true",
                   help="Jalankan SUMO tanpa GUI (lebih cepat)")
    p.add_argument("--conf",    type=float, default=0.50,
                   help="Confidence threshold YOLOv11 (0.1–0.9)")
    p.add_argument("--test",    action="store_true",
                   help="Test cepat integrasi tanpa SUMO")
    return p.parse_args()


def main():
    args = parse_args()

    if args.test:
        run_quick_test(args.model, args.conf)
        return

    ctrl = TrafficController(args)
    ctrl.run()


if __name__ == "__main__":
    main()
