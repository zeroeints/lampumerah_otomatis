# Rancangan Sistem Lampu Merah Otomatis (YOLO11 + Fuzzy Logic)

## 1. Tujuan
Membangun aplikasi yang dapat:
1. Memilih tipe simpang: **pertigaan** atau **perempatan**.
2. Upload video dari setiap lengan simpang (3 video untuk pertigaan, 4 video untuk perempatan).
3. Menghitung jumlah kendaraan per jenis (motor, mobil, bus, truk) menggunakan **YOLO11**.
4. Mengonversi jumlah kendaraan menjadi **beban lalu lintas berbobot**.
5. Menjalankan simulasi dua skenario:
   - Kontrol lampu **fixed-time** (tanpa fuzzy).
   - Kontrol lampu **adaptif fuzzy logic**.
6. Menampilkan perbandingan metrik: rata-rata waktu tunggu, kepadatan, panjang antrean, throughput, dll.

## 2. Scope Versi Awal (MVP)
1. GUI sederhana untuk memilih tipe simpang dan upload video.
2. Deteksi kendaraan berbasis file video (bukan live camera).
3. Simulasi berbasis time-step (misal 1 detik/step).
4. Tidak wajib terhubung SUMO pada MVP (bisa internal simulator dulu).
5. Hasil berupa tabel + grafik perbandingan Fixed vs Fuzzy.

## 3. Kebutuhan Fungsional
1. User memilih:
   - `Perempatan` -> wajib upload 4 video (`utara`, `timur`, `selatan`, `barat`).
   - `Pertigaan` -> wajib upload 3 video (misal `utara`, `timur`, `barat`).
2. Sistem validasi:
   - Format video (`.mp4`, `.avi`, `.mov`).
   - Durasi minimum (misal >= 30 detik).
   - Resolusi minimum (misal >= 480p).
3. Sistem deteksi kendaraan per frame atau per interval sampling.
4. Sistem klasifikasi objek ke kelas: `motor`, `mobil`, `bus`, `truk`.
5. Sistem hitung bobot kendaraan per lengan jalan.
6. Sistem simulasi phase lampu dan antrian kendaraan.
7. Sistem bandingkan hasil Fixed vs Fuzzy dengan metrik terukur.

## 4. Bobot Kendaraan (Konfigurabel)
Gunakan konsep ekuivalensi beban lalu lintas. Bobot awal (dapat dituning):

| Jenis | Bobot |
|---|---:|
| Motor | 1.0 |
| Mobil | 1.5 |
| Bus | 2.5 |
| Truk | 3.0 |

Rumus beban per lengan:

`beban_lengan = (motor*1.0) + (mobil*1.5) + (bus*2.5) + (truk*3.0)`

Nilai ini dipakai sebagai input fuzzy dan simulasi antrean.

## 5. Arsitektur Sistem
1. `GUI Layer`
   - Pilih simpang.
   - Upload video.
   - Tombol proses deteksi.
   - Tombol jalankan simulasi.
   - Dashboard hasil.
2. `Detection Layer (YOLO11)`
   - Load model `best.pt` / model custom.
   - Inferensi video per arah.
   - Tracking sederhana untuk menghindari double count (opsional awal: counting by line crossing).
3. `Traffic Feature Layer`
   - Agregasi count per arah per interval (misal per 5 detik).
   - Hitung beban berbobot.
4. `Control Layer`
   - `FixedTimeController`.
   - `FuzzyController`.
5. `Simulation Engine`
   - Menjalankan time-step, phase switching, queue update.
6. `Evaluation Layer`
   - Hitung metrik KPI.
   - Buat grafik dan ringkasan.

## 6. Desain GUI (Sederhana)
Rekomendasi stack: **Streamlit** (cepat untuk prototipe) atau **PySide6/Tkinter** (desktop native).

Halaman/Panel MVP:
1. **Setup Simpang**
   - Dropdown: `Pertigaan / Perempatan`.
   - Input parameter simulasi: durasi step, minimum green, yellow, all-red.
2. **Upload Video**
   - Upload sesuai jumlah lengan.
   - Preview frame awal.
3. **Deteksi & Validasi**
   - Tombol `Jalankan Deteksi YOLO11`.
   - Tabel count per jenis kendaraan per lengan.
4. **Simulasi**
   - Tombol `Simulasi Fixed` dan `Simulasi Fuzzy`.
5. **Hasil Perbandingan**
   - Grafik antrean terhadap waktu.
   - Grafik waiting time.
   - Tabel KPI final.

## 7. Logika Phase Lampu (Realistis)
Gunakan pendekatan **movement-based** dengan aturan konflik.

### 7.1 Definisi Movement (Perempatan)
Setiap lengan memiliki movement:
1. `Lurus`
2. `Belok kiri`
3. `Belok kanan`

Notasi contoh:
- `N_S`: dari Utara ke Selatan (lurus)
- `W_S`: dari Barat ke Selatan (belok kiri bila lalu lintas kiri)

### 7.2 Aturan Keselamatan Dasar
1. Movement yang berpotensi tabrakan **tidak boleh hijau bersamaan**.
2. Setiap perpindahan phase wajib:
   - `yellow` (misal 3 detik)
   - `all-red` (misal 1-2 detik)
3. Minimum green (misal 10 detik) agar tidak flicker.
4. Maksimum green (misal 60 detik) agar lengan lain tidak kelaparan.

### 7.3 Contoh Aturan Khusus Sesuai Permintaan
Permintaan Anda: ketika lampu hijau pada sisi bawah aktif, arus lurus di kanan-kiri harus merah, tetapi arus tertentu dari sisi kiri ke bawah boleh jalan.

Implementasi sebagai rule konflik kustom:
1. Jika movement utama aktif = `S_N` (dari bawah ke atas / fase bawah lurus), maka:
   - `E_W` dan `W_E` (lurus dari kanan/kiri) = **merah**.
   - Izinkan movement non-konflik terpilih, misal `W_S` = **hijau** (kiri ke bawah), jika tidak memotong jalur utama.
2. Rule ini dimasukkan ke **conflict matrix** agar bisa dikontrol konsisten.

### 7.4 Conflict Matrix
Bangun matriks `allowed[movement_i][movement_j]` bernilai `true/false`.
1. `false` jika geometri lintasan saling potong.
2. `true` jika paralel/tidak konflik.
3. Phase generator memilih set movement yang semuanya saling `true`.

Dengan ini aturan dunia nyata dapat dipaksakan tanpa hardcode berlebihan.

## 8. Fuzzy Logic Design
### 8.1 Input Fuzzy
Per phase gunakan agregat beban atau antrean:
1. `queue_load` (beban antrean saat ini)
2. `waiting_avg` (rata-rata waktu tunggu)
3. `arrival_rate` (opsional)

Minimal MVP cukup 2 input:
1. `queue_load`
2. `waiting_avg`

### 8.2 Membership Function (Contoh)
1. `queue_load`: `rendah`, `sedang`, `tinggi`
2. `waiting_avg`: `cepat`, `normal`, `lama`
3. Output `green_extension`: `pendek`, `sedang`, `panjang`

Rentang contoh:
1. `queue_load` 0-100
2. `waiting_avg` 0-180 detik
3. `green_extension` 0-30 detik

### 8.3 Rule Base (Contoh Inti)
1. IF `queue_load` tinggi AND `waiting_avg` lama THEN `green_extension` panjang
2. IF `queue_load` sedang AND `waiting_avg` normal THEN `green_extension` sedang
3. IF `queue_load` rendah AND `waiting_avg` cepat THEN `green_extension` pendek
4. IF `queue_load` tinggi AND `waiting_avg` cepat THEN `green_extension` sedang
5. IF `queue_load` rendah AND `waiting_avg` lama THEN `green_extension` sedang

Durasi hijau akhir:

`green_time = clamp(min_green + green_extension, min_green, max_green)`

## 9. Simulasi Fixed vs Fuzzy
### 9.1 Fixed-Time
1. Cycle tetap, contoh:
   - Phase A: 30 detik
   - Phase B: 30 detik
   - Yellow + all-red di antaranya
2. Tidak tergantung kondisi kepadatan.

### 9.2 Fuzzy Adaptive
1. Tiap pergantian phase, hitung input fuzzy dari kondisi terkini.
2. Tentukan green tiap phase secara dinamis.
3. Tetap patuhi batas keselamatan (min/max green + yellow + all-red).

## 10. Metrik Evaluasi
Hitung untuk kedua skenario:
1. `Average waiting time` (detik/kendaraan)
2. `Max waiting time`
3. `Average queue length` (kendaraan atau beban)
4. `Max queue length`
5. `Throughput` (kendaraan keluar per menit)
6. `Density index` (beban total/kapasitas)
7. `Phase fairness` (selisih layanan antar lengan)

Output akhir:
1. Tabel perbandingan Fixed vs Fuzzy.
2. Persentase improvement:
   - `% penurunan waktu tunggu`
   - `% penurunan antrean`
   - `% kenaikan throughput`

## 11. Struktur Proyek yang Disarankan
```text
traffic_ai/
  app.py                        # Entry GUI
  config/
    settings.yaml
    vehicle_weights.yaml
    phase_rules_perempatan.yaml
    phase_rules_pertigaan.yaml
  detection/
    yolo_detector.py
    tracker_counter.py
  control/
    fixed_time.py
    fuzzy_controller.py
    conflict_matrix.py
  simulation/
    engine.py
    intersection.py
    metrics.py
  ui/
    pages_setup.py
    pages_upload.py
    pages_results.py
  data/
    uploads/
    processed/
  output/
    charts/
    reports/
```

## 12. Rencana Implementasi Bertahap
### Tahap 1 - Fondasi
1. Setup project dan dependency.
2. Bangun GUI upload (3/4 video).
3. Implement YOLO inference per video + rekap count per kelas.

### Tahap 2 - Simulasi Dasar
1. Bangun simulator queue sederhana.
2. Implement kontrol fixed-time.
3. Tampilkan metrik baseline.

### Tahap 3 - Fuzzy Adaptive
1. Implement membership + rule base.
2. Integrasikan fuzzy untuk menentukan green duration.
3. Bandingkan hasil dengan baseline fixed-time.

### Tahap 4 - Logika Realistis Simpang
1. Definisikan movement dan conflict matrix.
2. Tambahkan rule khusus geometri simpang sesuai kebutuhan lapangan.
3. Validasi safety constraint (yellow/all-red/min-green).

### Tahap 5 - Pelaporan
1. Dashboard grafik dan tabel.
2. Export laporan (`.csv`/`.png`/`.md`).
3. Dokumentasi eksperimen.

## 13. Risiko dan Mitigasi
1. **Double counting kendaraan**
   - Mitigasi: line-crossing + tracker (ByteTrack/DeepSORT ringan).
2. **Akurasi model rendah pada malam/hujan**
   - Mitigasi: finetune dataset lokal, confidence tuning.
3. **Simulasi tidak mencerminkan kondisi real**
   - Mitigasi: kalibrasi parameter arrival/departure dari data lapangan.
4. **Fuzzy overfit ke satu skenario**
   - Mitigasi: uji beberapa set video dan tuning rule.

## 14. Definisi Sukses
Sistem dianggap sukses jika:
1. GUI berjalan dan user bisa upload video sesuai tipe simpang.
2. Kendaraan per kelas terdeteksi dan terbobot.
3. Simulasi Fixed dan Fuzzy sama-sama berjalan tanpa error.
4. Hasil komparasi metrik muncul jelas.
5. Rule fase konflik berjalan aman dan konsisten dengan logika dunia nyata.

## 15. Next Deliverable Setelah Dokumen Ini
1. Implementasi kerangka folder + file awal.
2. Prototipe GUI upload.
3. Modul deteksi YOLO11 sederhana.
4. Simulator fixed-time baseline.
5. Integrasi fuzzy + dashboard hasil.
