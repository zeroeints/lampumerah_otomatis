import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import pandas as pd
import streamlit as st
from ultralytics import YOLO

from traffic_simulation import run_comparison
from sumo_simulation import run_comparison_sumo as run_comparison_sumo_orig
from sumo_simulation_opt import run_comparison_sumo as run_comparison_sumo_opt


VEHICLE_WEIGHTS = {
    "motor": 0.4,
    "mobil": 1.0,
    "bus": 2.3,
    "truk": 2.3,
}

COCO_TO_LOCAL = {
    "motorcycle": "motor",
    "car": "mobil",
    "bus": "bus",
    "truck": "truk",
}


def normalize_class_name(name: str) -> str:
    key = (name or "").strip().lower()
    if key in VEHICLE_WEIGHTS:
        return key
    return COCO_TO_LOCAL.get(key, "")


@st.cache_resource(show_spinner=False)
def load_model(model_path: str) -> YOLO:
    mp = Path(model_path)
    if not mp.exists():
        raise FileNotFoundError(f"Model tidak ditemukan: {mp.resolve()}")
    return YOLO(str(mp))


def init_count_dict() -> Dict[str, int]:
    return {k: 0 for k in VEHICLE_WEIGHTS.keys()}


def _center_distance(box_a: Tuple[float, float, float, float], box_b: Tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    acx = (ax1 + ax2) / 2.0
    acy = (ay1 + ay2) / 2.0
    bcx = (bx1 + bx2) / 2.0
    bcy = (by1 + by2) / 2.0
    return ((acx - bcx) ** 2 + (acy - bcy) ** 2) ** 0.5


def process_video(
    model: YOLO,
    video_path: str,
    conf: float,
    frame_stride: int,
    max_frames: int,
    output_video_path: str = None,
    imgsz: int = 480,
    progress_placeholder = None,
    direction_label: str = "",
) -> Tuple[Dict[str, int], int]:
    """
    Hitung kendaraan unik secara aproksimasi.
    Deteksi mentah per frame akan menggelembungkan hitungan, jadi deteksi
    dipadankan lintas frame dengan tracker centroid sederhana.
    """
    counts = init_count_dict()
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Gagal membuka video: {video_path}")

    frame_index = 0
    processed = 0
    next_track_id = 1
    tracks: Dict[int, Dict[str, object]] = {}

    out = None
    if output_video_path:
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        out_fps = fps / frame_stride
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_video_path, fourcc, out_fps, (width, height))

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            frame_index += 1
            if frame_stride > 1 and (frame_index % frame_stride != 0):
                continue

            results = model.predict(frame, conf=conf, verbose=False, imgsz=imgsz)
            
            if out is not None and results:
                annotated_frame = results[0].plot()
                out.write(annotated_frame)

            boxes = results[0].boxes if results else []
            detections: List[Dict[str, object]] = []
            for box in boxes:
                cls_id = int(box.cls[0])
                cls_name = results[0].names.get(cls_id, "")
                local = normalize_class_name(cls_name)
                if local:
                    coords = tuple(float(v) for v in box.xyxy[0].tolist())
                    detections.append({"label": local, "bbox": coords})

            used_tracks = set()
            updated_tracks = set()
            frame_match_distance = max(frame.shape[0], frame.shape[1]) * 0.04

            for det in detections:
                best_track_id = None
                best_distance = frame_match_distance
                for track_id, track in tracks.items():
                    if track["label"] != det["label"] or track_id in used_tracks:
                        continue
                    dist = _center_distance(track["bbox"], det["bbox"])
                    if dist < best_distance:
                        best_distance = dist
                        best_track_id = track_id

                if best_track_id is None:
                    track_id = next_track_id
                    next_track_id += 1
                    tracks[track_id] = {
                        "label": det["label"],
                        "bbox": det["bbox"],
                        "missed": 0,
                    }
                    counts[det["label"]] += 1
                    updated_tracks.add(track_id)
                    used_tracks.add(track_id)
                    continue

                tracks[best_track_id]["bbox"] = det["bbox"]
                tracks[best_track_id]["missed"] = 0
                updated_tracks.add(best_track_id)
                used_tracks.add(best_track_id)

            expired = []
            max_missed = max(2, frame_stride + 1)
            for track_id, track in tracks.items():
                if track_id in updated_tracks:
                    continue
                track["missed"] = int(track["missed"]) + 1
                if int(track["missed"]) > max_missed:
                    expired.append(track_id)
            for track_id in expired:
                tracks.pop(track_id, None)

            processed += 1
            if progress_placeholder and (processed % 10 == 0 or processed == 1):
                progress_placeholder.markdown(f"⏳ **[{direction_label}]** Memproses frame: `{processed}` / `{max_frames}`...")
            if processed >= max_frames:
                break
    finally:
        cap.release()
        if out is not None:
            out.release()

    return counts, processed


def to_weighted(counts: Dict[str, int]) -> float:
    return round(sum(counts[k] * VEHICLE_WEIGHTS[k] for k in VEHICLE_WEIGHTS), 2)


def get_dirs_for_phase(phase_name: str, simpang: str) -> List[str]:
    name = phase_name.upper()
    dirs = []
    
    if "UTARA" in name or "NS" in name or "N_MAIN" in name:
        dirs.append("Utara")
    if "SELATAN" in name or "NS" in name or "S_MAIN" in name or "BAWAH" in name:
        dirs.append("Selatan")
    if "TIMUR" in name or "EW" in name or "E_MAIN" in name:
        dirs.append("Timur")
    if "BARAT" in name or "EW" in name or "W_MAIN" in name or "KIRI" in name:
        dirs.append("Barat")
        
    dirs = list(dict.fromkeys(dirs))
    
    if simpang == "Pertigaan" and "Selatan" in dirs:
        dirs.remove("Selatan")
        
    return dirs


def extract_direction_cycles(timeline: List[Dict], simpang: str) -> Dict[str, List[Dict]]:
    if not timeline:
        return {}
    
    if simpang == "Pertigaan":
        directions = ["Utara", "Timur", "Barat"]
    else:
        directions = ["Utara", "Timur", "Selatan", "Barat"]
        
    dir_events = {d: [] for d in directions}
    total_steps = len(timeline)
    
    for d in directions:
        in_green = False
        green_start = None
        green_dur = 0
        last_green_end = None
        
        for t in timeline:
            phase_name = t["phase"]
            status = t["status"]
            
            green_dirs = get_dirs_for_phase(phase_name, simpang)
            is_green_now = (status == "GREEN" and d in green_dirs)
            
            if is_green_now:
                if not in_green:
                    in_green = True
                    green_start = t["step"]
                    if last_green_end is not None:
                        red_dur = green_start - last_green_end
                        if dir_events[d]:
                            dir_events[d][-1]["red_duration"] = red_dur
                green_dur += 1
            else:
                if in_green:
                    in_green = False
                    last_green_end = t["step"]
                    dir_events[d].append({
                        "direction": d,
                        "cycle_num": len(dir_events[d]) + 1,
                        "green_duration": green_dur,
                        "red_duration": 0,
                    })
                    green_dur = 0
                    
        if in_green:
            dir_events[d].append({
                "direction": d,
                "cycle_num": len(dir_events[d]) + 1,
                "green_duration": green_dur,
                "red_duration": 0,
            })
            
        for i in range(len(dir_events[d])):
            if dir_events[d][i]["red_duration"] == 0:
                if i > 0:
                    dir_events[d][i]["red_duration"] = dir_events[d][i-1]["red_duration"]
                else:
                    dir_events[d][i]["red_duration"] = max(0, total_steps - dir_events[d][i]["green_duration"])
                    
    return dir_events


def render_cycle_analysis(fixed_tl: List[Dict], fuzzy_tl: List[Dict], simpang: str = "Perempatan", key_suffix: str = "live"):
    if not fixed_tl or not fuzzy_tl:
        st.warning("Data timeline tidak lengkap untuk analisis durasi lampu.")
        return

    fixed_cycles = extract_direction_cycles(fixed_tl, simpang)
    fuzzy_cycles = extract_direction_cycles(fuzzy_tl, simpang)
    
    if not fixed_cycles or not fuzzy_cycles:
        st.warning("Tidak berhasil mendeteksi siklus lampu per ruas jalan.")
        return

    directions = list(fixed_cycles.keys())
    
    st.subheader("⏱️ Analisis Siklus Lampu Per Ruas Jalan (Utara, Selatan, Timur, Barat)")
    st.markdown("Berikut adalah rincian perbandingan durasi lampu hijau dan merah untuk setiap siklus di masing-masing ruas simpang.")
    
    selected_dir = st.selectbox(
        "Pilih Ruas Jalan untuk Visualisasi",
        directions,
        key=f"dir_selector_{key_suffix}"
    )
    
    df_fixed = pd.DataFrame(fixed_cycles[selected_dir])
    df_fuzzy = pd.DataFrame(fuzzy_cycles[selected_dir])
    
    df_compare_green = pd.merge(
        df_fixed[["cycle_num", "green_duration"]].rename(columns={"green_duration": "Fixed-Time Hijau"}),
        df_fuzzy[["cycle_num", "green_duration"]].rename(columns={"green_duration": "Fuzzy Adaptif Hijau"}),
        on="cycle_num",
        how="outer"
    ).set_index("cycle_num")
    
    df_compare_red = pd.merge(
        df_fixed[["cycle_num", "red_duration"]].rename(columns={"red_duration": "Fixed-Time Merah"}),
        df_fuzzy[["cycle_num", "red_duration"]].rename(columns={"red_duration": "Fuzzy Adaptif Merah"}),
        on="cycle_num",
        how="outer"
    ).set_index("cycle_num")
    
    tab_chart1, tab_chart2 = st.tabs(["📈 Grafik Lampu Hijau", "📈 Grafik Lampu Merah"])
    with tab_chart1:
        st.write(f"**Perbandingan Durasi Hijau per Siklus - Ruas {selected_dir}**")
        st.line_chart(df_compare_green)
    with tab_chart2:
        st.write(f"**Perbandingan Durasi Merah per Siklus - Ruas {selected_dir}**")
        st.line_chart(df_compare_red)
        
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        st.markdown(f"##### 📋 Skenario **Fixed-Time** (Ruas {selected_dir})")
        df_fixed_disp = df_fixed[["cycle_num", "green_duration", "red_duration"]].rename(
            columns={
                "cycle_num": "Siklus",
                "green_duration": "Hijau (detik)",
                "red_duration": "Merah (detik)"
            }
        )
        st.dataframe(df_fixed_disp, use_container_width=True, hide_index=True)
        
    with col_t2:
        st.markdown(f"##### 📋 Skenario **Fuzzy Adaptif** (Ruas {selected_dir})")
        df_fuzzy_disp = df_fuzzy[["cycle_num", "green_duration", "red_duration"]].rename(
            columns={
                "cycle_num": "Siklus",
                "green_duration": "Hijau (detik)",
                "red_duration": "Merah (detik)"
            }
        )
        st.dataframe(df_fuzzy_disp, use_container_width=True, hide_index=True)


def show_admin_history() -> None:
    st.markdown("""
        <div style='text-align: center; padding: 1.5rem 0; animation: fadeInDown 0.8s ease-out;'>
            <h1 style='font-size: 3rem; margin-bottom: 0.5rem;'>Data Center & Riwayat 📊</h1>
            <p style='color: #94a3b8; font-size: 1.1rem; max-width: 600px; margin: 0 auto;'>
                Melihat, membandingkan, dan mengunduh data analitik dari simulasi lalu lintas sebelumnya secara real-time.
            </p>
        </div>
        <hr style='border-color: rgba(255,255,255,0.1); margin-bottom: 2rem;'>
    """, unsafe_allow_html=True)

    import glob
    import os
    import json
    from pathlib import Path
    
    log_files = sorted(glob.glob("output/sim_log_*.json"), reverse=True)
    
    if not log_files:
        st.warning("Tidak ditemukan riwayat simulasi di folder `output/`.")
        return
        
    log_options = {}
    for lf in log_files:
        filename = Path(lf).name
        ts = filename.replace("sim_log_", "").replace(".json", "")
        try:
            date_str = f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:13]}:{ts[13:15]}"
        except Exception:
            date_str = ts
        
        try:
            with open(lf, "r", encoding="utf-8") as f:
                data = json.load(f)
                meta = data.get("metadata", {})
                summary = data.get("summary", {})
                
                if "fixed" in summary or "fixed_timeline" in data:
                    avg_wait_fuzzy = summary.get("fuzzy", {}).get("avg_wait_s", 0.0)
                    avg_wait_fixed = summary.get("fixed", {}).get("avg_wait_s", 0.0)
                    label = f"📅 {date_str} | perbandingan (Fuzzy: {avg_wait_fuzzy:.2f}s vs Fixed: {avg_wait_fixed:.2f}s)"
                else:
                    avg_wait = summary.get("avg_wait_s", 0.0)
                    label = f"📅 {date_str} | single-run (Avg Wait: {avg_wait:.2f}s)"
        except Exception:
            label = f"📅 {date_str} ({filename})"
            
        log_options[label] = lf
        
    selected_label = st.selectbox("Pilih Riwayat Simulasi", list(log_options.keys()))
    selected_file = log_options[selected_label]
    
    try:
        with open(selected_file, "r", encoding="utf-8") as f:
            log_data = json.load(f)
    except Exception as e:
        st.error(f"Gagal memuat file log: {e}")
        return
        
    meta = log_data.get("metadata", {})
    summary = log_data.get("summary", {})
    
    st.markdown("---")
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("📋 Informasi Sesi")
        st.write(f"**Mahasiswa:** {meta.get('mahasiswa', '-')}")
        st.write(f"**NIM:** {meta.get('nim', '-')}")
        st.write(f"**Institusi:** {meta.get('institusi', '-')}")
        st.write(f"**Tanggal:** {meta.get('tanggal', meta.get('tanggal_simulasi', '-'))}")
        st.write(f"**Tipe Simpang:** {meta.get('simpang', '-')}")
        st.write(f"**Engine:** {meta.get('sim_engine', 'Internal Python')}")
        if "use_opt_fuzzy" in meta:
            st.write(f"**Fuzzy Optimasi:** {'Ya (Skripsi)' if meta.get('use_opt_fuzzy') else 'Tidak (Original)'}")
        if "weighted_by_dir" in meta:
            st.write("**Beban Kendaraan per Arah:**")
            st.json(meta.get("weighted_by_dir", {}))
        
    with col2:
        st.subheader("📊 Metrik Utama (Summary)")
        
        is_comparison = "fixed" in summary or "fixed_timeline" in log_data
        
        if is_comparison:
            fixed_kpi = summary.get("fixed", {})
            fuzzy_kpi = summary.get("fuzzy", {})
            
            kpi_cols = st.columns(3)
            f0_wait = fixed_kpi.get("avg_wait_s", 0.0)
            f1_wait = fuzzy_kpi.get("avg_wait_s", 0.0)
            imp_wait = ((f0_wait - f1_wait) / max(abs(f0_wait), 1e-6)) * 100.0
            kpi_cols[0].metric("Avg Wait Time (Fuzzy)", f"{f1_wait:.2f} s", delta=f"-{imp_wait:.1f}% Wait" if imp_wait > 0 else f"+{-imp_wait:.1f}% Wait", delta_color="inverse")
            
            f0_q = fixed_kpi.get("avg_queue", 0.0)
            f1_q = fuzzy_kpi.get("avg_queue", 0.0)
            imp_q = ((f0_q - f1_q) / max(abs(f0_q), 1e-6)) * 100.0
            kpi_cols[1].metric("Avg Queue (Fuzzy)", f"{f1_q:.2f} kend", delta=f"-{imp_q:.1f}% Queue" if imp_q > 0 else f"+{-imp_q:.1f}% Queue", delta_color="inverse")
            
            f0_tp = fixed_kpi.get("throughput_per_min", 0.0)
            f1_tp = fuzzy_kpi.get("throughput_per_min", 0.0)
            imp_tp = ((f1_tp - f0_tp) / max(abs(f0_tp), 1e-6)) * 100.0
            kpi_cols[2].metric("Throughput/min (Fuzzy)", f"{f1_tp:.2f} kend", delta=f"+{imp_tp:.1f}% Flows" if imp_tp > 0 else f"-{-imp_tp:.1f}% Flows")
            
            with st.expander("Metrik Kinerja Lengkap"):
                compare_rows = log_data.get("compare_rows", [])
                if compare_rows:
                    st.dataframe(pd.DataFrame(compare_rows), use_container_width=True)
                else:
                    st.write(f"Fixed KPI: {fixed_kpi}")
                    st.write(f"Fuzzy KPI: {fuzzy_kpi}")
        else:
            kpi_cols = st.columns(3)
            kpi_cols[0].metric("Avg Waiting Time", f"{summary.get('avg_wait_s', 0.0):.2f} s")
            kpi_cols[1].metric("Avg Queue Length", f"{summary.get('avg_queue', 0.0):.2f} kend")
            kpi_cols[2].metric("Max Waiting Time", f"{summary.get('max_wait_s', 0.0):.2f} s")
            
            kpi_cols_2 = st.columns(3)
            kpi_cols_2[0].metric("Max Queue Length", f"{summary.get('max_queue', 0.0):.2f} kend")
            kpi_cols_2[1].metric("Total Steps", f"{summary.get('total_steps', 0)}")
            kpi_cols_2[2].metric("Avg Latency", f"{summary.get('avg_lat_ms', 0.0):.1f} ms")

    st.markdown("---")
    
    if is_comparison:
        st.subheader("📈 Analisis Grafik Perbandingan")
        fixed_tl = log_data.get("fixed_timeline", [])
        fuzzy_tl = log_data.get("fuzzy_timeline", [])
        
        if fixed_tl and fuzzy_tl:
            fixed_df = pd.DataFrame(fixed_tl)
            fuzzy_df = pd.DataFrame(fuzzy_tl)
            
            if "queue_total" in fixed_df.columns and "queue_total" in fuzzy_df.columns:
                st.write("**Panjang Antrean Terhadap Waktu (Fixed-time vs Fuzzy Adaptif)**")
                f_q = fixed_df[["step", "queue_total"]].rename(columns={"queue_total": "Fixed-Time"})
                fz_q = fuzzy_df[["step", "queue_total"]].rename(columns={"queue_total": "Fuzzy Adaptif"})
                chart_df = f_q.merge(fz_q, on="step", how="inner").set_index("step")
                st.line_chart(chart_df)
                
            if "avg_wait_s" in fixed_df.columns and "avg_wait_s" in fuzzy_df.columns:
                st.write("**Waktu Tunggu Terhadap Waktu (Fixed-time vs Fuzzy Adaptif)**")
                f_w = fixed_df[["step", "avg_wait_s"]].rename(columns={"avg_wait_s": "Fixed-Time"})
                fz_w = fuzzy_df[["step", "avg_wait_s"]].rename(columns={"avg_wait_s": "Fuzzy Adaptif"})
                chart_w_df = f_w.merge(fz_w, on="step", how="inner").set_index("step")
                st.line_chart(chart_w_df)
                
            render_cycle_analysis(fixed_tl, fuzzy_tl, meta.get("simpang", "Perempatan"), key_suffix=selected_file)
    else:
        st.subheader("📈 Grafik Kinerja Sesi Adaptif")
        records = log_data.get("records", [])
        if records:
            df_rec = pd.DataFrame(records)
            st.write("**Grafik Waktu Tunggu vs Panjang Antrean**")
            chart_data = df_rec[["step", "wait", "queue"]].rename(columns={"wait": "Waktu Tunggu (s)", "queue": "Panjang Antrean"})
            st.line_chart(chart_data.set_index("step"))
            
            dirs = [d for d in ["N", "S", "E", "W"] if d in df_rec.columns]
            if dirs:
                st.write("**Beban Kendaraan Per Lajur (Utara, Selatan, Timur, Barat)**")
                st.line_chart(df_rec[["step"] + dirs].set_index("step"))

    st.markdown("---")
    
    ts = Path(selected_file).name.replace("sim_log_", "").replace(".json", "")
    laporan_img_path = f"output/laporan_{ts}.png"
    if os.path.exists(laporan_img_path):
        st.subheader("🖼️ Laporan Hasil Cetak (Matplotlib)")
        st.image(laporan_img_path, caption=f"Grafik Analisis Matplotlib Sesi {ts}", use_container_width=True)

    col_act1, col_act2 = st.columns([1, 1])
    
    with col_act1:
        csv_filename = f"output/sim_data_{ts}.csv"
        if os.path.exists(csv_filename):
            with open(csv_filename, "r", encoding="utf-8") as csv_f:
                csv_data = csv_f.read()
            st.download_button(
                label="📥 Unduh Data CSV Sesi Ini",
                data=csv_data,
                file_name=f"sim_data_{ts}.csv",
                mime="text/csv",
                type="primary"
            )
        elif is_comparison:
            try:
                fixed_df_download = pd.DataFrame(fixed_tl)
                fuzzy_df_download = pd.DataFrame(fuzzy_tl)
                fixed_df_download["Mode"] = "Fixed-Time"
                fuzzy_df_download["Mode"] = "Fuzzy"
                combined_df = pd.concat([fixed_df_download, fuzzy_df_download], ignore_index=True)
                csv_data = combined_df.to_csv(index=False)
                st.download_button(
                    label="📥 Unduh Data CSV Sesi Ini",
                    data=csv_data,
                    file_name=f"sim_comparison_{ts}.csv",
                    mime="text/csv",
                    type="primary"
                )
            except Exception:
                pass
                
    with col_act2:
        if st.button("🗑️ Hapus Riwayat Ini", type="secondary", use_container_width=True):
            try:
                os.remove(selected_file)
                if os.path.exists(laporan_img_path):
                    os.remove(laporan_img_path)
                csv_path = f"output/sim_data_{ts}.csv"
                if os.path.exists(csv_path):
                    os.remove(csv_path)
                st.success("Riwayat berhasil dihapus!")
                st.rerun()
            except Exception as e:
                st.error(f"Gagal menghapus riwayat: {e}")


def inject_custom_css():
    st.markdown("""
        <style>
        /* Modern Dark Theme with Glassmorphism */
        .stApp {
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            color: #f8fafc;
        }
        
        /* Typography and Headings */
        h1 {
            font-family: 'Inter', sans-serif;
            font-weight: 800 !important;
            background: -webkit-linear-gradient(45deg, #38bdf8, #818cf8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            animation: fadeInDown 0.8s ease-out;
            letter-spacing: -1px;
        }
        h2, h3 {
            font-family: 'Inter', sans-serif;
            color: #e2e8f0 !important;
            animation: fadeIn 1s ease-in-out;
        }
        
        /* Metric Cards */
        [data-testid="stMetricValue"] {
            font-size: 2.5rem !important;
            font-weight: 800;
            color: #38bdf8 !important;
        }
        [data-testid="stMetricLabel"] {
            font-size: 0.95rem !important;
            color: #94a3b8 !important;
            text-transform: uppercase;
            letter-spacing: 1.5px;
            font-weight: 700;
        }
        [data-testid="stMetricDelta"] {
            font-size: 1rem !important;
        }
        div[data-testid="metric-container"] {
            background: rgba(30, 41, 59, 0.7);
            border-radius: 16px;
            padding: 20px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            animation: fadeInUp 0.6s ease-out backwards;
        }
        div[data-testid="metric-container"]:hover {
            transform: translateY(-8px) scale(1.02);
            box-shadow: 0 15px 30px rgba(56, 189, 248, 0.15);
            border-color: rgba(56, 189, 248, 0.4);
        }
        
        /* Buttons */
        .stButton > button {
            background: linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%);
            color: white;
            border-radius: 12px;
            border: none;
            padding: 0.6rem 1.8rem;
            font-weight: 700;
            transition: all 0.3s ease;
            text-transform: uppercase;
            letter-spacing: 1px;
            box-shadow: 0 4px 15px rgba(14, 165, 233, 0.3);
        }
        .stButton > button:hover {
            transform: translateY(-3px) scale(1.02);
            box-shadow: 0 8px 25px rgba(14, 165, 233, 0.5);
            color: white;
            border: none;
        }
        
        /* Sidebar */
        [data-testid="stSidebar"] {
            background-color: rgba(15, 23, 42, 0.95) !important;
            border-right: 1px solid rgba(255, 255, 255, 0.05);
        }
        
        /* Expander */
        .streamlit-expanderHeader {
            background-color: rgba(30, 41, 59, 0.5);
            border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 0.05);
            font-weight: 600;
        }
        
        /* File Uploader */
        [data-testid="stFileUploader"] {
            background: rgba(30, 41, 59, 0.4);
            border-radius: 12px;
            padding: 15px;
            border: 2px dashed rgba(148, 163, 184, 0.3);
            transition: all 0.3s ease;
        }
        [data-testid="stFileUploader"]:hover {
            border-color: #38bdf8;
            background: rgba(30, 41, 59, 0.6);
        }
        
        /* Animations */
        @keyframes fadeInDown {
            from { opacity: 0; transform: translateY(-30px); }
            to { opacity: 1; transform: translateY(0); }
        }
        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(30px); }
            to { opacity: 1; transform: translateY(0); }
        }
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
        
        /* Dataframes */
        [data-testid="stDataFrame"] {
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 8px 20px rgba(0, 0, 0, 0.2);
            border: 1px solid rgba(255, 255, 255, 0.05);
        }
        
        /* Success info box override */
        div.stAlert > div {
            border-radius: 12px;
            border: none;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }
        </style>
    """, unsafe_allow_html=True)

def main() -> None:
    st.set_page_config(page_title="Sistem Cerdas Lalu Lintas", layout="wide", page_icon="🚦")
    inject_custom_css()

    with st.sidebar:
        st.markdown("<h2 style='text-align: center; font-size: 1.8rem; margin-bottom: 1rem;'>🎛️ Dashboard Control</h2>", unsafe_allow_html=True)
        menu = st.radio("Navigasi Menu Utama", ["Deteksi & Simulasi", "Admin History (Riwayat)"])
        st.divider()

    if menu == "Admin History (Riwayat)":
        show_admin_history()
        return

    st.markdown("""
        <div style='text-align: center; padding: 2rem 0; animation: fadeInDown 0.8s ease-out;'>
            <h1 style='font-size: 3.5rem; margin-bottom: 0.5rem; line-height: 1.2;'>Sistem Cerdas Kendali Lalu Lintas 🚦</h1>
            <p style='color: #94a3b8; font-size: 1.2rem; font-weight: 500; max-width: 800px; margin: 0 auto;'>
                Analisis Volume Kendaraan Berbasis Computer Vision (YOLOv11) & Optimasi Lampu Lalu Lintas menggunakan Logika Fuzzy
            </p>
        </div>
        <hr style='border-color: rgba(255,255,255,0.1); margin-bottom: 2rem;'>
    """, unsafe_allow_html=True)

    with st.sidebar:
        st.header("Pengaturan")
        model_path = st.text_input("Path model YOLO11", value="best.pt")
        conf = st.slider("Confidence", min_value=0.10, max_value=0.95, value=0.50, step=0.05)
        frame_stride = st.number_input("Ambil setiap N frame", min_value=1, max_value=20, value=3, step=1)
        max_frames = st.number_input("Maks frame per video", min_value=30, max_value=100000, value=18000, step=100)
        imgsz = st.selectbox("Ukuran Gambar Deteksi (imgsz YOLO)", [320, 480, 640], index=1, help="Lebih kecil = jauh lebih cepat di CPU. Default 480.")
        save_annotated = st.checkbox("Simpan video hasil deteksi (.mp4)", value=True, help="Menyimpan video dengan bounding box. Matikan jika ingin proses lebih cepat.")
        st.divider()
        st.subheader("Simulasi Lampu")
        sim_engine = st.selectbox("Engine Simulasi", ["Internal Python", "SUMO/TraCI"], index=0)
        sim_steps = st.number_input("Durasi simulasi (step/detik)", min_value=300, max_value=7200, value=1800, step=300)
        min_green = st.number_input("Min green (detik)", min_value=5, max_value=40, value=10, step=1)
        max_green = st.number_input("Max green (detik)", min_value=20, max_value=120, value=60, step=1)
        yellow = st.number_input("Yellow (detik)", min_value=2, max_value=8, value=3, step=1)
        all_red = st.number_input("All-red (detik)", min_value=0, max_value=5, value=1, step=1)
        sumo_cfg = st.text_input("SUMO config (.sumocfg)", value="sumo_config/intersection.sumocfg")
        tl_id = st.text_input("Traffic Light ID", value="J_center")
        use_sumo_gui = st.checkbox("Tampilkan SUMO GUI", value=False)
        use_custom_fourway = st.checkbox("Rule kustom perempatan (TraCI state)", value=True)
        use_opt_fuzzy = st.checkbox("Gunakan Optimasi Fuzzy (Skripsi)", value=True, help="Aktifkan untuk menggunakan fuzzy_controller_opt (2 input) dan sumo_simulation_opt.")

    simpang = st.radio("Tipe simpang", ["Perempatan", "Pertigaan"], horizontal=True)
    directions: List[str] = ["Utara", "Timur", "Selatan", "Barat"] if simpang == "Perempatan" else ["Utara", "Timur", "Barat"]

    uploads = {}
    st.subheader("Upload Video")
    cols = st.columns(len(directions))
    for idx, direction in enumerate(directions):
        with cols[idx]:
            uploads[direction] = st.file_uploader(
                f"Video {direction}",
                type=["mp4", "avi", "mov", "mkv"],
                key=f"video_{direction}",
            )

    if st.button("Proses YOLO11", type="primary"):
        missing = [d for d in directions if uploads.get(d) is None]
        if missing:
            st.error(f"Video belum lengkap. Kurang: {', '.join(missing)}")
            return

        try:
            model = load_model(model_path)
        except Exception as exc:
            st.error(str(exc))
            return

        from datetime import datetime
        run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        result_rows = []
        total_counts = init_count_dict()

        progress = st.progress(0)
        status = st.empty()
        total_dir = len(directions)

        annotated_vids = {}

        progress_placeholder = st.empty()
        for i, direction in enumerate(directions, start=1):
            status.info(f"Memproses {direction} (Arah {i}/{total_dir})...")
            uploaded = uploads[direction]
            suffix = Path(uploaded.name).suffix or ".mp4"

            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(uploaded.read())
                temp_path = tmp.name

            output_video_path = f"output/annotated_{run_ts}_{direction}.mp4" if save_annotated else None
            if save_annotated:
                annotated_vids[direction] = output_video_path

            try:
                counts, processed = process_video(
                    model=model,
                    video_path=temp_path,
                    conf=conf,
                    frame_stride=int(frame_stride),
                    max_frames=int(max_frames),
                    output_video_path=output_video_path,
                    imgsz=imgsz,
                    progress_placeholder=progress_placeholder,
                    direction_label=direction,
                )
            finally:
                Path(temp_path).unlink(missing_ok=True)

            for k in total_counts:
                total_counts[k] += counts[k]

            result_rows.append(
                {
                    "Arah": direction,
                    "Frame Diproses": processed,
                    "Motor": counts["motor"],
                    "Mobil": counts["mobil"],
                    "Bus": counts["bus"],
                    "Truk": counts["truk"],
                    "Beban Berbobot": to_weighted(counts),
                }
            )
            progress.progress(i / total_dir)

        progress_placeholder.empty()
        status.success("Selesai.")
        df = pd.DataFrame(result_rows)
        st.subheader("Rekap Per Arah (YOLO11)")
        st.dataframe(df, use_container_width=True)

        total_weight = to_weighted(total_counts)
        kpi_cols = st.columns(5)
        kpi_cols[0].metric("Total Motor", total_counts["motor"])
        kpi_cols[1].metric("Total Mobil", total_counts["mobil"])
        kpi_cols[2].metric("Total Bus", total_counts["bus"])
        kpi_cols[3].metric("Total Truk", total_counts["truk"])
        kpi_cols[4].metric("Total Beban", f"{total_weight:.2f}")

        st.subheader("Asumsi Bobot Kendaraan")
        st.json(VEHICLE_WEIGHTS)
        weighted_by_dir = {row["Arah"]: row["Beban Berbobot"] for row in result_rows}
        st.subheader("Input Beban Simulasi")
        st.write(weighted_by_dir)

        if sim_engine == "SUMO/TraCI":
            try:
                if use_opt_fuzzy:
                    sim_res = run_comparison_sumo_opt(
                        sumo_cfg=sumo_cfg,
                        tl_id=tl_id,
                        intersection_type=simpang,
                        weighted_by_dir=weighted_by_dir,
                        duration_steps=int(sim_steps),
                        min_green=int(min_green),
                        max_green=int(max_green),
                        yellow=int(yellow),
                        all_red=int(all_red),
                        use_gui=use_sumo_gui,
                        custom_fourway_logic=use_custom_fourway,
                    )
                    st.success("Simulasi menggunakan SUMO/TraCI dengan Optimasi Fuzzy (Skripsi).")
                else:
                    sim_res = run_comparison_sumo_orig(
                        sumo_cfg=sumo_cfg,
                        tl_id=tl_id,
                        intersection_type=simpang,
                        weighted_by_dir=weighted_by_dir,
                        duration_steps=int(sim_steps),
                        min_green=int(min_green),
                        max_green=int(max_green),
                        yellow=int(yellow),
                        all_red=int(all_red),
                        use_gui=use_sumo_gui,
                        custom_fourway_logic=use_custom_fourway,
                    )
                    st.success("Simulasi menggunakan SUMO/TraCI (Original).")
                sim_backend = "sumo"
            except Exception as exc:
                st.error(f"Gagal menjalankan SUMO/TraCI: {exc}")
                st.info("Fallback ke engine internal Python.")
                sim_res = run_comparison(
                    intersection_type=simpang,
                    weighted_by_dir=weighted_by_dir,
                    duration_steps=int(sim_steps),
                    min_green=int(min_green),
                    max_green=int(max_green),
                    yellow=int(yellow),
                    all_red=int(all_red),
                )
                sim_backend = "internal"
        else:
            sim_res = run_comparison(
                intersection_type=simpang,
                weighted_by_dir=weighted_by_dir,
                duration_steps=int(sim_steps),
                min_green=int(min_green),
                max_green=int(max_green),
                yellow=int(yellow),
                all_red=int(all_red),
            )
            sim_backend = "internal"

        fixed_kpi = sim_res["fixed"]["kpi"]
        fuzzy_kpi = sim_res["fuzzy"]["kpi"]
        compare_rows = []
        keys = [
            ("avg_wait_s", "Avg Waiting Time (s)", False),
            ("avg_red_s", "Avg Red-Light Duration (s)", False),
            ("max_red_s", "Max Red-Light Duration (s)", False),
            ("avg_queue", "Avg Queue", False),
            ("max_queue", "Max Queue", False),
            ("throughput_per_min", "Throughput / min", True),
            ("density_index", "Density Index", False),
            ("total_served", "Total Served", True),
        ]
        if sim_backend != "sumo":
            keys.append(("phase_fairness_gap", "Fairness Gap", False))
        for key, label, higher_better in keys:
            f0 = fixed_kpi[key]
            f1 = fuzzy_kpi[key]
            if higher_better:
                improvement = ((f1 - f0) / max(abs(f0), 1e-6)) * 100.0
            else:
                improvement = ((f0 - f1) / max(abs(f0), 1e-6)) * 100.0
            compare_rows.append(
                {
                    "Metrik": label,
                    "Fixed": round(f0, 3),
                    "Fuzzy": round(f1, 3),
                    "Improvement %": round(improvement, 2),
                }
            )

        # Simpan hasil ke file log di folder output
        import json
        ts = run_ts
        log_filename = f"output/sim_log_{ts}.json"
        csv_filename = f"output/sim_data_{ts}.csv"
        
        # Beritahu user lokasi penyimpanan video teranotasi
        for direction, vid_path in annotated_vids.items():
            st.info(f"🎥 Video teranotasi ({direction}) disimpan di: `{vid_path}`")
        
        streamlit_log = {
            "metadata": {
                "mahasiswa": "Mohammad Filla Firdaus",
                "nim": "2215354055",
                "institusi": "Politeknik Negeri Bali",
                "tanggal": datetime.now().isoformat(),
                "model": "YOLOv11 + Logika Fuzzy (Streamlit)",
                "sim_engine": sim_engine,
                "simpang": simpang,
                "use_opt_fuzzy": use_opt_fuzzy if sim_engine == "SUMO/TraCI" else False,
                "weighted_by_dir": weighted_by_dir
            },
            "summary": {
                "fixed": fixed_kpi,
                "fuzzy": fuzzy_kpi
            },
            "fixed_timeline": sim_res["fixed"]["timeline"],
            "fuzzy_timeline": sim_res["fuzzy"]["timeline"],
            "compare_rows": compare_rows
        }
        
        try:
            with open(log_filename, "w", encoding="utf-8") as log_f:
                json.dump(streamlit_log, log_f, indent=2)
            st.info(f"💾 Riwayat simulasi disimpan ke: `{log_filename}`")
            
            # Simpan ke CSV juga
            fixed_df_download = pd.DataFrame(sim_res["fixed"]["timeline"])
            fuzzy_df_download = pd.DataFrame(sim_res["fuzzy"]["timeline"])
            fixed_df_download["Mode"] = "Fixed-Time"
            fuzzy_df_download["Mode"] = "Fuzzy"
            combined_df = pd.concat([fixed_df_download, fuzzy_df_download], ignore_index=True)
            combined_df.to_csv(csv_filename, index=False, encoding="utf-8")
            st.info(f"💾 Data CSV disimpan ke: `{csv_filename}`")
        except Exception as e:
            st.error(f"Gagal menyimpan riwayat simulasi: {e}")

        st.subheader("Perbandingan Fixed-Time vs Fuzzy")
        st.dataframe(pd.DataFrame(compare_rows), use_container_width=True)
        st.caption("Durasi merah dihitung sebagai lama sebuah arah berada di kondisi non-hijau sebelum mendapat hijau lagi.")

        fixed_df = pd.DataFrame(sim_res["fixed"]["timeline"])[["step", "queue_total"]].rename(columns={"queue_total": "Fixed"})
        fuzzy_df = pd.DataFrame(sim_res["fuzzy"]["timeline"])[["step", "queue_total"]].rename(columns={"queue_total": "Fuzzy"})
        chart_df = fixed_df.merge(fuzzy_df, on="step", how="inner").set_index("step")
        st.line_chart(chart_df)
        
        render_cycle_analysis(sim_res["fixed"]["timeline"], sim_res["fuzzy"]["timeline"], simpang)

        st.subheader("Rencana Fase Lampu (Conflict-aware)")
        for i, phase in enumerate(sim_res["fuzzy"]["phase_plan"], start=1):
            green_dirs = phase.get("green_dirs", phase.get("dirs", []))
            notes = phase.get("notes", "-")
            st.markdown(f"{i}. **{phase.get('name', f'Phase {i}')}** | Green: `{', '.join(green_dirs)}` | {notes}")


if __name__ == "__main__":
    main()
