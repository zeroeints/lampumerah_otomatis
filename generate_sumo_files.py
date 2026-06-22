"""
=============================================================================
generate_sumo_files.py — Generate File SUMO yang Valid
=============================================================================
Script ini akan membuat file SUMO yang benar menggunakan netconvert
(tool bawaan SUMO). Jalankan SEKALI sebelum simulasi.

Cara jalankan:
    python generate_sumo_files.py

Yang akan dibuat:
    sumo_config/
        intersection.nod.xml     ← definisi node/titik (input netconvert)
        intersection.edg.xml     ← definisi jalan (input netconvert)
        intersection.con.xml     ← definisi koneksi lajur
        intersection.tll.xml     ← definisi lampu lalu lintas
        intersection.net.xml     ← jaringan final (OUTPUT netconvert) ✓
        vehicles.rou.xml         ← rute dan arus kendaraan
        intersection.sumocfg     ← konfigurasi utama SUMO
=============================================================================
"""
import os
import sys
import subprocess
from pathlib import Path

# ── Temukan SUMO_HOME ──────────────────────────────────────────
SUMO_HOME = os.environ.get("SUMO_HOME", "")
COMMON_PATHS = [
    r"C:\Program Files (x86)\Eclipse\Sumo",
    r"C:\Program Files\Eclipse\Sumo",
    r"C:\Sumo",
    r"/usr/share/sumo",
    r"/usr/local/share/sumo",
]

if not SUMO_HOME:
    for p in COMMON_PATHS:
        if Path(p).exists():
            SUMO_HOME = p
            os.environ["SUMO_HOME"] = p
            break

if not SUMO_HOME:
    print("[ERROR] SUMO_HOME tidak ditemukan!")
    print("        Set manual: set SUMO_HOME=C:\\Program Files (x86)\\Eclipse\\Sumo")
    sys.exit(1)

print(f"[✓] SUMO_HOME: {SUMO_HOME}")

# Tentukan path netconvert
if sys.platform == "win32":
    NETCONVERT = Path(SUMO_HOME) / "bin" / "netconvert.exe"
else:
    NETCONVERT = Path(SUMO_HOME) / "bin" / "netconvert"

if not NETCONVERT.exists():
    # Coba dari PATH langsung
    NETCONVERT = "netconvert"

# Buat folder output
OUT = Path("sumo_config")
OUT.mkdir(exist_ok=True)
Path("output").mkdir(exist_ok=True)
Path("logs").mkdir(exist_ok=True)
print(f"[✓] Folder sumo_config/ dibuat")


# ══════════════════════════════════════════════════════════════
# STEP 1: Buat intersection.nod.xml  (Node / Titik Persimpangan)
# ══════════════════════════════════════════════════════════════
nod_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<nodes>
    <!-- Persimpangan pusat dengan lampu lalu lintas -->
    <node id="J_center" x="0.00"    y="0.00"    type="traffic_light"/>
    <!-- Ujung lengan jalan (batas area simulasi) -->
    <node id="J_N"      x="0.00"    y="200.00"  type="dead_end"/>
    <node id="J_S"      x="0.00"    y="-200.00" type="dead_end"/>
    <node id="J_E"      x="200.00"  y="0.00"    type="dead_end"/>
    <node id="J_W"      x="-200.00" y="0.00"    type="dead_end"/>
</nodes>
"""

# ══════════════════════════════════════════════════════════════
# STEP 2: Buat intersection.edg.xml  (Ruas Jalan / Edge)
# ══════════════════════════════════════════════════════════════
edg_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<edges>
    <!-- Jalan MASUK ke persimpangan (4 arah) -->
    <!-- numLanes=2: lajur 0=lurus, lajur 1=belok kiri -->
    <edge id="E_N_in"  from="J_N"      to="J_center" numLanes="2" speed="13.89" priority="12"/>
    <edge id="E_S_in"  from="J_S"      to="J_center" numLanes="2" speed="13.89" priority="12"/>
    <edge id="E_E_in"  from="J_E"      to="J_center" numLanes="2" speed="13.89" priority="12"/>
    <edge id="E_W_in"  from="J_W"      to="J_center" numLanes="2" speed="13.89" priority="12"/>

    <!-- Jalan KELUAR dari persimpangan (4 arah) -->
    <edge id="E_N_out" from="J_center" to="J_N"      numLanes="2" speed="13.89" priority="12"/>
    <edge id="E_S_out" from="J_center" to="J_S"      numLanes="2" speed="13.89" priority="12"/>
    <edge id="E_E_out" from="J_center" to="J_E"      numLanes="2" speed="13.89" priority="12"/>
    <edge id="E_W_out" from="J_center" to="J_W"      numLanes="2" speed="13.89" priority="12"/>
</edges>
"""

# ══════════════════════════════════════════════════════════════
# STEP 3: Buat intersection.con.xml  (Koneksi antar Lajur)
# ══════════════════════════════════════════════════════════════
con_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<connections>
    <!-- Dari UTARA -->
    <!-- Lajur 0: lurus ke Selatan -->
    <connection from="E_N_in" to="E_S_out" fromLane="0" toLane="0"/>
    <!-- Lajur 1: belok kiri ke Timur -->
    <connection from="E_N_in" to="E_E_out" fromLane="1" toLane="0"/>

    <!-- Dari SELATAN -->
    <!-- Lajur 0: lurus ke Utara -->
    <connection from="E_S_in" to="E_N_out" fromLane="0" toLane="0"/>
    <!-- Lajur 1: belok kiri ke Barat -->
    <connection from="E_S_in" to="E_W_out" fromLane="1" toLane="0"/>

    <!-- Dari TIMUR -->
    <!-- Lajur 0: lurus ke Barat -->
    <connection from="E_E_in" to="E_W_out" fromLane="0" toLane="0"/>
    <!-- Lajur 1: belok kiri ke Selatan -->
    <connection from="E_E_in" to="E_S_out" fromLane="1" toLane="0"/>

    <!-- Dari BARAT -->
    <!-- Lajur 0: lurus ke Timur -->
    <connection from="E_W_in" to="E_E_out" fromLane="0" toLane="0"/>
    <!-- Lajur 1: belok kiri ke Utara -->
    <connection from="E_W_in" to="E_N_out" fromLane="1" toLane="0"/>
</connections>
"""

# ══════════════════════════════════════════════════════════════
# STEP 4: Buat intersection.tll.xml  (Program Lampu Lalu Lintas)
# ══════════════════════════════════════════════════════════════
# State string: posisi 0-7 = 8 koneksi di atas (urutan dari con.xml)
# G=Hijau  y=Kuning  r=Merah
tll_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<tlLogics>
    <tlLogic id="J_center" type="static" programID="adaptive_fuzzy" offset="0">
        <!--
            Urutan koneksi (sesuai con.xml):
            0: N→S  1: N→E  2: S→N  3: S→W  4: E→W  5: E→S  6: W→E  7: W→N

            Fase 0: NS HIJAU  (N→S, N→E, S→N, S→W = GGGG) | EW MERAH (E→W, E→S, W→E, W→N = rrrr)
            Fase 1: NS KUNING (yyyy) | EW MERAH (rrrr)
            Fase 2: EW HIJAU  (NS MERAH = rrrr) | EW HIJAU (GGGG)
            Fase 3: EW KUNING (rrrr) | EW KUNING (yyyy)
        -->
        <phase duration="30" state="GGGGrrrr" name="NS_GREEN"/>
        <phase duration="3"  state="yyyyrrrr" name="NS_YELLOW"/>
        <phase duration="30" state="rrrrGGGG" name="EW_GREEN"/>
        <phase duration="3"  state="rrrryyyy" name="EW_YELLOW"/>
    </tlLogic>
</tlLogics>
"""

# ══════════════════════════════════════════════════════════════
# STEP 5: Buat vehicles.rou.xml  (Arus Kendaraan)
# ══════════════════════════════════════════════════════════════
rou_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<!--
    Distribusi kendaraan (kondisi lalu lintas Bali):
      Mobil  40% | Motor 45% | Bus 8% | Truk 7%

    3 Periode:
      P1 (0-600s)    : Volume rendah  ~400 kend/jam
      P2 (600-2400s) : JAM SIBUK      ~900 kend/jam (NS lebih padat)
      P3 (2400-3600s): Volume sedang  ~550 kend/jam
-->
<routes>
    <!-- Tipe kendaraan -->
    <vType id="Mobil" length="4.5" accel="2.6" decel="4.5" sigma="0.5"
           maxSpeed="13.89" minGap="2.5" color="0,0.9,1"    guiShape="passenger"/>
    <vType id="Motor" length="2.0" accel="3.5" decel="5.0" sigma="0.6"
           maxSpeed="16.67" minGap="1.0" color="0.49,0.23,0.93" guiShape="motorcycle"/>
    <vType id="Bus"   length="12.0" accel="1.2" decel="4.0" sigma="0.3"
           maxSpeed="11.11" minGap="3.0" color="0.96,0.62,0.04" guiShape="bus"/>
    <vType id="Truk"  length="10.0" accel="1.0" decel="3.5" sigma="0.3"
           maxSpeed="11.11" minGap="3.5" color="0.93,0.28,0.60" guiShape="truck"/>

    <!-- Rute lurus -->
    <route id="r_NS" edges="E_N_in E_S_out"/>
    <route id="r_SN" edges="E_S_in E_N_out"/>
    <route id="r_EW" edges="E_E_in E_W_out"/>
    <route id="r_WE" edges="E_W_in E_E_out"/>
    <!-- Rute belok -->
    <route id="r_NE" edges="E_N_in E_E_out"/>
    <route id="r_SW" edges="E_S_in E_W_out"/>
    <route id="r_ES" edges="E_E_in E_S_out"/>
    <route id="r_WN" edges="E_W_in E_N_out"/>

    <!-- ═══ P1: Volume Rendah (0-600s) ═══ -->
    <flow id="p1_N_M"  type="Mobil" route="r_NS" begin="0"   end="600"  vehsPerHour="160" departLane="best" departSpeed="max"/>
    <flow id="p1_N_Mo" type="Motor" route="r_NS" begin="0"   end="600"  vehsPerHour="180" departLane="best" departSpeed="max"/>
    <flow id="p1_N_B"  type="Bus"   route="r_NS" begin="0"   end="600"  vehsPerHour="32"  departLane="best" departSpeed="max"/>
    <flow id="p1_N_T"  type="Truk"  route="r_NS" begin="0"   end="600"  vehsPerHour="28"  departLane="best" departSpeed="max"/>

    <flow id="p1_S_M"  type="Mobil" route="r_SN" begin="0"   end="600"  vehsPerHour="152" departLane="best" departSpeed="max"/>
    <flow id="p1_S_Mo" type="Motor" route="r_SN" begin="0"   end="600"  vehsPerHour="171" departLane="best" departSpeed="max"/>
    <flow id="p1_S_B"  type="Bus"   route="r_SN" begin="0"   end="600"  vehsPerHour="30"  departLane="best" departSpeed="max"/>
    <flow id="p1_S_T"  type="Truk"  route="r_SN" begin="0"   end="600"  vehsPerHour="27"  departLane="best" departSpeed="max"/>

    <flow id="p1_E_M"  type="Mobil" route="r_EW" begin="0"   end="600"  vehsPerHour="120" departLane="best" departSpeed="max"/>
    <flow id="p1_E_Mo" type="Motor" route="r_EW" begin="0"   end="600"  vehsPerHour="135" departLane="best" departSpeed="max"/>
    <flow id="p1_E_B"  type="Bus"   route="r_EW" begin="0"   end="600"  vehsPerHour="24"  departLane="best" departSpeed="max"/>
    <flow id="p1_E_T"  type="Truk"  route="r_EW" begin="0"   end="600"  vehsPerHour="21"  departLane="best" departSpeed="max"/>

    <flow id="p1_W_M"  type="Mobil" route="r_WE" begin="0"   end="600"  vehsPerHour="128" departLane="best" departSpeed="max"/>
    <flow id="p1_W_Mo" type="Motor" route="r_WE" begin="0"   end="600"  vehsPerHour="144" departLane="best" departSpeed="max"/>
    <flow id="p1_W_B"  type="Bus"   route="r_WE" begin="0"   end="600"  vehsPerHour="26"  departLane="best" departSpeed="max"/>
    <flow id="p1_W_T"  type="Truk"  route="r_WE" begin="0"   end="600"  vehsPerHour="22"  departLane="best" departSpeed="max"/>

    <!-- ═══ P2: JAM SIBUK (600-2400s) — NS jauh lebih padat ═══ -->
    <flow id="p2_N_M"  type="Mobil" route="r_NS" begin="600" end="2400" vehsPerHour="360" departLane="best" departSpeed="max"/>
    <flow id="p2_N_Mo" type="Motor" route="r_NS" begin="600" end="2400" vehsPerHour="405" departLane="best" departSpeed="max"/>
    <flow id="p2_N_B"  type="Bus"   route="r_NS" begin="600" end="2400" vehsPerHour="72"  departLane="best" departSpeed="max"/>
    <flow id="p2_N_T"  type="Truk"  route="r_NS" begin="600" end="2400" vehsPerHour="63"  departLane="best" departSpeed="max"/>

    <flow id="p2_S_M"  type="Mobil" route="r_SN" begin="600" end="2400" vehsPerHour="340" departLane="best" departSpeed="max"/>
    <flow id="p2_S_Mo" type="Motor" route="r_SN" begin="600" end="2400" vehsPerHour="382" departLane="best" departSpeed="max"/>
    <flow id="p2_S_B"  type="Bus"   route="r_SN" begin="600" end="2400" vehsPerHour="68"  departLane="best" departSpeed="max"/>
    <flow id="p2_S_T"  type="Truk"  route="r_SN" begin="600" end="2400" vehsPerHour="60"  departLane="best" departSpeed="max"/>

    <flow id="p2_E_M"  type="Mobil" route="r_EW" begin="600" end="2400" vehsPerHour="160" departLane="best" departSpeed="max"/>
    <flow id="p2_E_Mo" type="Motor" route="r_EW" begin="600" end="2400" vehsPerHour="180" departLane="best" departSpeed="max"/>
    <flow id="p2_E_B"  type="Bus"   route="r_EW" begin="600" end="2400" vehsPerHour="32"  departLane="best" departSpeed="max"/>
    <flow id="p2_E_T"  type="Truk"  route="r_EW" begin="600" end="2400" vehsPerHour="28"  departLane="best" departSpeed="max"/>

    <flow id="p2_W_M"  type="Mobil" route="r_WE" begin="600" end="2400" vehsPerHour="172" departLane="best" departSpeed="max"/>
    <flow id="p2_W_Mo" type="Motor" route="r_WE" begin="600" end="2400" vehsPerHour="193" departLane="best" departSpeed="max"/>
    <flow id="p2_W_B"  type="Bus"   route="r_WE" begin="600" end="2400" vehsPerHour="34"  departLane="best" departSpeed="max"/>
    <flow id="p2_W_T"  type="Truk"  route="r_WE" begin="600" end="2400" vehsPerHour="31"  departLane="best" departSpeed="max"/>

    <!-- ═══ P3: Volume Sedang (2400-3600s) ═══ -->
    <flow id="p3_N_M"  type="Mobil" route="r_NS" begin="2400" end="3600" vehsPerHour="220" departLane="best" departSpeed="max"/>
    <flow id="p3_N_Mo" type="Motor" route="r_NS" begin="2400" end="3600" vehsPerHour="247" departLane="best" departSpeed="max"/>
    <flow id="p3_N_B"  type="Bus"   route="r_NS" begin="2400" end="3600" vehsPerHour="44"  departLane="best" departSpeed="max"/>
    <flow id="p3_N_T"  type="Truk"  route="r_NS" begin="2400" end="3600" vehsPerHour="38"  departLane="best" departSpeed="max"/>

    <flow id="p3_S_M"  type="Mobil" route="r_SN" begin="2400" end="3600" vehsPerHour="208" departLane="best" departSpeed="max"/>
    <flow id="p3_S_Mo" type="Motor" route="r_SN" begin="2400" end="3600" vehsPerHour="234" departLane="best" departSpeed="max"/>
    <flow id="p3_S_B"  type="Bus"   route="r_SN" begin="2400" end="3600" vehsPerHour="42"  departLane="best" departSpeed="max"/>
    <flow id="p3_S_T"  type="Truk"  route="r_SN" begin="2400" end="3600" vehsPerHour="36"  departLane="best" departSpeed="max"/>

    <flow id="p3_E_M"  type="Mobil" route="r_EW" begin="2400" end="3600" vehsPerHour="196" departLane="best" departSpeed="max"/>
    <flow id="p3_E_Mo" type="Motor" route="r_EW" begin="2400" end="3600" vehsPerHour="220" departLane="best" departSpeed="max"/>
    <flow id="p3_E_B"  type="Bus"   route="r_EW" begin="2400" end="3600" vehsPerHour="39"  departLane="best" departSpeed="max"/>
    <flow id="p3_E_T"  type="Truk"  route="r_EW" begin="2400" end="3600" vehsPerHour="35"  departLane="best" departSpeed="max"/>

    <flow id="p3_W_M"  type="Mobil" route="r_WE" begin="2400" end="3600" vehsPerHour="204" departLane="best" departSpeed="max"/>
    <flow id="p3_W_Mo" type="Motor" route="r_WE" begin="2400" end="3600" vehsPerHour="229" departLane="best" departSpeed="max"/>
    <flow id="p3_W_B"  type="Bus"   route="r_WE" begin="2400" end="3600" vehsPerHour="41"  departLane="best" departSpeed="max"/>
    <flow id="p3_W_T"  type="Truk"  route="r_WE" begin="2400" end="3600" vehsPerHour="36"  departLane="best" departSpeed="max"/>

    <!-- Kendaraan belok (variasi realistis) -->
    <flow id="bNE" type="Mobil" route="r_NE" begin="0" end="3600" vehsPerHour="48" departLane="best" departSpeed="max"/>
    <flow id="bSW" type="Mobil" route="r_SW" begin="0" end="3600" vehsPerHour="44" departLane="best" departSpeed="max"/>
    <flow id="bES" type="Motor" route="r_ES" begin="0" end="3600" vehsPerHour="54" departLane="best" departSpeed="max"/>
    <flow id="bWN" type="Motor" route="r_WN" begin="0" end="3600" vehsPerHour="50" departLane="best" departSpeed="max"/>
</routes>
"""

# ══════════════════════════════════════════════════════════════
# STEP 6: Buat intersection.sumocfg
# ══════════════════════════════════════════════════════════════
cfg_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <input>
        <net-file    value="intersection.net.xml"/>
        <route-files value="vehicles.rou.xml"/>
    </input>
    <time>
        <begin       value="0"/>
        <end         value="3600"/>
        <step-length value="1.0"/>
    </time>
    <o>
        <summary-output  value="../output/summary.xml"/>
        <tripinfo-output value="../output/tripinfo.xml"/>
        <queue-output    value="../output/queue.xml"/>
    </o>
    <processing>
        <time-to-teleport    value="300"/>
        <collision.action    value="warn"/>
    </processing>
    <report>
        <verbose     value="false"/>
        <no-warnings value="true"/>
        <log         value="../logs/sumo_run.log"/>
    </report>
    <gui_only>
        <start       value="true"/>
        <delay       value="50"/>
        <window-size value="1100,750"/>
        <window-pos  value="100,50"/>
    </gui_only>
</configuration>
"""

# ══════════════════════════════════════════════════════════════
# TULIS SEMUA FILE INPUT
# ══════════════════════════════════════════════════════════════
print("\n[*] Menulis file input...")

files = {
    "intersection.nod.xml": nod_xml,
    "intersection.edg.xml": edg_xml,
    "intersection.con.xml": con_xml,
    "intersection.tll.xml": tll_xml,
    "vehicles.rou.xml"    : rou_xml,
    "intersection.sumocfg": cfg_xml,
}

for fname, content in files.items():
    path = OUT / fname
    path.write_text(content, encoding="utf-8")
    print(f"  [✓] {fname}")

# ══════════════════════════════════════════════════════════════
# STEP 7: Jalankan netconvert untuk generate intersection.net.xml
# ══════════════════════════════════════════════════════════════
print("\n[*] Menjalankan netconvert untuk generate intersection.net.xml...")

cmd = [
    str(NETCONVERT),
    "--node-files",       str(OUT / "intersection.nod.xml"),
    "--edge-files",       str(OUT / "intersection.edg.xml"),
    "--connection-files", str(OUT / "intersection.con.xml"),
    "--tllogic-files",    str(OUT / "intersection.tll.xml"),
    "--output-file",      str(OUT / "intersection.net.xml"),
    "--no-warnings",
    "--default.junctions.keep-clear", "false",
]

try:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    if result.returncode == 0:
        net_path = OUT / "intersection.net.xml"
        size_kb  = net_path.stat().st_size / 1024
        print(f"  [✓] intersection.net.xml berhasil dibuat! ({size_kb:.1f} KB)")
    else:
        print(f"  [✗] netconvert gagal!")
        print(f"      STDOUT: {result.stdout[:300]}")
        print(f"      STDERR: {result.stderr[:300]}")
        sys.exit(1)

except FileNotFoundError:
    print(f"  [✗] netconvert tidak ditemukan di: {NETCONVERT}")
    print(f"\n  Coba jalankan manual di Command Prompt:")
    print(f'  netconvert --node-files sumo_config\\intersection.nod.xml \\')
    print(f'             --edge-files sumo_config\\intersection.edg.xml \\')
    print(f'             --connection-files sumo_config\\intersection.con.xml \\')
    print(f'             --tllogic-files sumo_config\\intersection.tll.xml \\')
    print(f'             --output-file sumo_config\\intersection.net.xml')
    sys.exit(1)

except subprocess.TimeoutExpired:
    print("  [✗] netconvert timeout!")
    sys.exit(1)

# ══════════════════════════════════════════════════════════════
# STEP 8: Verifikasi semua file ada
# ══════════════════════════════════════════════════════════════
print("\n[*] Verifikasi file yang dibutuhkan...")

required = [
    "intersection.net.xml",
    "vehicles.rou.xml",
    "intersection.sumocfg",
]

all_ok = True
for fname in required:
    p = OUT / fname
    if p.exists():
        print(f"  [✓] sumo_config/{fname}  ({p.stat().st_size/1024:.1f} KB)")
    else:
        print(f"  [✗] sumo_config/{fname}  TIDAK ADA!")
        all_ok = False

# ══════════════════════════════════════════════════════════════
# SELESAI
# ══════════════════════════════════════════════════════════════
if all_ok:
    print("\n" + "="*55)
    print("  [✓] SEMUA FILE SIAP!")
    print("="*55)
    print("\n  Sekarang jalankan sistem:")
    print("    python main_controller.py --test   ← verifikasi dulu")
    print("    python main_controller.py           ← simulasi penuh")
    print()
else:
    print("\n  [✗] Ada file yang gagal dibuat. Periksa error di atas.")
    sys.exit(1)
