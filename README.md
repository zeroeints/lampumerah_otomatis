# 🚦 Sistem Pengendalian Lampu Lalu Lintas Adaptif
## YOLOv11 + Logika Fuzzy + SUMO TraCI

**Mohammad Filla Firdaus | NIM. 2215354055 | Politeknik Negeri Bali | TRPL 2026**

---

## 📁 Isi Folder

```
📦 sistem_lalu_lintas/
├── 🐍 main_controller.py         ← FILE UTAMA — jalankan ini
├── 🐍 analyze_results.py         ← Analisis & grafik hasil simulasi
├── 🐍 app_yolo11_gui.py          ← GUI Streamlit (opsional)
├── 🦇 JALANKAN.bat               ← Klik 2x untuk jalankan di Windows
├── 🧠 fuzzy/
│   └── fuzzy_controller.py       ← Modul Logika Fuzzy
├── 🚗 sumo_config/
│   ├── intersection.sumocfg      ← Konfigurasi simulasi SUMO
│   ├── intersection.net.xml      ← Jaringan jalan persimpangan
│   └── vehicles.rou.xml          ← Definisi arus kendaraan
├── 📊 output/                    ← Hasil simulasi (dibuat otomatis)
└── 📋 logs/                      ← Log sistem (dibuat otomatis)
```

> **⚠️ Tambahkan `best.pt` ke folder ini sebelum menjalankan!**

---

## ⚡ Cara Menjalankan (Windows)

### Cara Termudah — Klik 2x
```
Klik 2x file JALANKAN.bat → pilih opsi sesuai kebutuhan
```

### Cara Manual (Command Prompt / PowerShell)

**1. Install dependensi (sekali saja):**
```cmd
pip install ultralytics scikit-fuzzy scipy opencv-python matplotlib numpy streamlit pandas sqlalchemy alembic pymysql
```

**2. Set SUMO_HOME (tiap sesi baru):**
```cmd
set SUMO_HOME=C:\Program Files (x86)\Eclipse\Sumo
```
> Sesuaikan path dengan lokasi instalasi SUMO di komputer Anda

**3. Test integrasi dulu:**
```cmd
python main_controller.py --test
```

**4. Jalankan simulasi penuh:**
```cmd
python main_controller.py
```

**5. Analisis hasil:**
```cmd
python analyze_results.py
```

---

## 🖥️ GUI Streamlit (Opsional)

Untuk antarmuka visual interaktif:

```cmd
pip install streamlit pandas
streamlit run app_yolo11_gui.py
```

> Membutuhkan modul tambahan `traffic_simulation` dan `sumo_simulation` yang di-import oleh `app_yolo11_gui.py`.

---

## MySQL + Alembic Logging

Semua run simulasi bisa direkam ke MySQL, termasuk:
- ringkasan KPI per run
- event fase lampu (`green_start`, `yellow_start`, `all_red_start`, `green_extend`, `green_cut`)
- metrik per langkah simulasi
- antrean per arah per langkah
- total hijau/merah, rata-rata, maksimum, dan jumlah hijau per arah

**1. Buat database MySQL:**
```sql
CREATE DATABASE traffic_simulation;
```

**2. Set koneksi database:**
```cmd
set TRAFFIC_SIM_DB_URL=mysql+pymysql://root@127.0.0.1:3306/traffic_simulation
set TRAFFIC_SIM_DB_ENABLED=1
```

**3. Jalankan migrasi Alembic:**
```cmd
alembic upgrade head
```

**4. Jalankan GUI atau simulasi seperti biasa**

Jika `TRAFFIC_SIM_DB_URL` tidak diset, aplikasi akan memakai default lokal `mysql+pymysql://root@127.0.0.1:3306/traffic_simulation`.

---

## 🎛️ Opsi Parameter

```cmd
python main_controller.py [opsi]

  --model best.pt         Path ke model YOLOv11 (default: best.pt)
  --sumo-cfg <path>       Path ke file .sumocfg (default: sumo_config/intersection.sumocfg)
  --tl-id J_center        ID traffic light di SUMO (default: J_center)
  --steps 3600            Jumlah langkah simulasi, 1 langkah = 1 detik (default: 3600)
  --nogui                 Tanpa GUI SUMO, lebih cepat
  --conf 0.50             Confidence threshold YOLOv11 (default: 0.50)
  --test                  Test cepat integrasi tanpa simulasi penuh
```

### Contoh:
```cmd
REM Simulasi 30 menit tanpa GUI (untuk pengujian cepat)
python main_controller.py --steps 1800 --nogui

REM Gunakan threshold lebih rendah (lebih banyak deteksi)
python main_controller.py --conf 0.40

REM Simulasi penuh 1 jam dengan GUI
python main_controller.py --steps 3600
```

---

## 📊 Analisis Hasil

Setelah simulasi selesai, jalankan:
```cmd
python analyze_results.py
```

Akan menghasilkan:
- **Tabel ringkasan** di konsol (metrik sistem adaptif)
- **Grafik 6 panel** di `output/laporan_*.png` berisi:
  - Waktu tunggu sistem adaptif
  - Kendaraan per lajur (hasil YOLOv11)
  - Durasi hijau adaptif per langkah
  - Panjang antrean
  - Latency inferensi YOLO
  - Tabel ringkasan metrik

> **Catatan:** Perbandingan dengan fixed-time memerlukan simulasi terpisah menggunakan mode fixed-time. Sistem tidak menghasilkan estimasi palsu.

---

## 🔧 Troubleshooting

### ❌ `best.pt tidak ditemukan`
Salin `best.pt` ke folder yang sama dengan `main_controller.py`.

### ❌ `TraCI tidak tersedia` / SUMO tidak terhubung
Sistem masih bisa jalan dalam **mode simulasi internal** (tanpa SUMO).
Untuk menghubungkan ke SUMO:
```cmd
set SUMO_HOME=C:\Program Files (x86)\Eclipse\Sumo
```
Pastikan path sesuai dengan lokasi instalasi SUMO.

### ❌ `No module named skfuzzy`
```cmd
pip install scikit-fuzzy scipy
```

### ❌ Latency inferensi sangat tinggi (>1000ms)
- Gunakan GPU jika tersedia (otomatis terdeteksi)
- Atau ganti model ke yang lebih ringan (model nano lebih cepat)

### ❌ `sumo-gui.exe not found`
SUMO sudah terinstall tapi binary tidak di PATH. Gunakan path lengkap:
```cmd
set SUMO_HOME=C:\Program Files (x86)\Eclipse\Sumo
```

### ⚠️ `Class mismatch!` warning saat startup
Model `best.pt` memiliki nama kelas yang berbeda dari yang diharapkan (`Mobil`, `Motor`, `Bus`, `Truk`). Sesuaikan `CLASS_NAMES` di `main_controller.py` agar cocok dengan output `model.names`.

---

## 🔄 Alur Kerja Sistem

```
   SUMO Simulator
        │ Frame screenshot (640×640)
        ▼
   YOLOv11 (best.pt)
        │ counts = {N:12, S:8, E:3, W:5}  ← per lajur
        │ latency ≈ 20–80ms
        ▼
   Fuzzy Logic Controller
        │ Fuzzifikasi → Rules → Defuzzifikasi Centroid
        │ NS_dur = 45s, EW_dur = 18s
        ▼
   TraCI.setPhaseDuration()
        │ Kirim perintah ke SUMO
        ▼
   SUMO jalankan dengan durasi baru
        │
        ▼
   Catat: waktu tunggu, antrean, latency
```

---

## 📐 Logika Fuzzy (Sesuai Proposal Bab 3)

**Input:** Jumlah kendaraan per lajur (0–30)

| Fungsi MF | Tipe | Parameter |
|-----------|------|-----------|
| Sedikit | Trapezoid | [0, 0, 5, 12] |
| Sedang | Segitiga | [5, 12, 20] |
| Padat | Trapezoid | [15, 22, 30, 30] |

**Rules:**
- IF Sedikit → Durasi Pendek (≈15s)
- IF Sedang → Durasi Sedang (≈30s)
- IF Padat → Durasi Panjang (≈55s)

**Defuzzifikasi:** Metode Centroid

---

*Dosen Pembimbing: I Nyoman Eddy Indrayana, S.Kom., M.T. | NIP. 197602202006041001*
