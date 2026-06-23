"""
app_yolo11_gui_opt.py — Versi OPTIMASI dari app_yolo11_gui.py
=============================================================================
Satu-satunya perubahan: import `run_comparison_sumo` dari `sumo_simulation_opt`
(versi optimasi) alih-alih `sumo_simulation` (versi asli).

Cara menjalankan:
    streamlit run app_yolo11_gui_opt.py

Cara mengembalikan ke versi asli:
    streamlit run app_yolo11_gui.py
=============================================================================
"""
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import pandas as pd
import streamlit as st
from ultralytics import YOLO

from traffic_simulation import run_comparison
from sumo_simulation_opt import run_comparison_sumo


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

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            frame_index += 1
            if frame_stride > 1 and (frame_index % frame_stride != 0):
                continue

            results = model.predict(frame, conf=conf, verbose=False)
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
            if processed >= max_frames:
                break
    finally:
        cap.release()

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


def main() -> None:
    st.set_page_config(page_title="YOLO11 Traffic Analyzer", layout="wide")
    st.title("Analisis Kendaraan Simpang (YOLO11)")
    st.caption("Pilih pertigaan/perempatan, upload video, lalu hitung kendaraan berbobot.")

    with st.sidebar:
        st.header("Pengaturan")
        model_path = st.text_input("Path model YOLO11", value="best (2).pt")
        conf = st.slider("Confidence", min_value=0.10, max_value=0.95, value=0.50, step=0.05)
        frame_stride = st.number_input("Ambil setiap N frame", min_value=1, max_value=20, value=3, step=1)
        max_frames = st.number_input("Maks frame per video", min_value=30, max_value=5000, value=600, step=30)
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

        result_rows = []
        total_counts = init_count_dict()

        progress = st.progress(0)
        status = st.empty()
        total_dir = len(directions)

        for i, direction in enumerate(directions, start=1):
            status.info(f"Memproses {direction}...")
            uploaded = uploads[direction]
            suffix = Path(uploaded.name).suffix or ".mp4"

            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(uploaded.read())
                temp_path = tmp.name

            try:
                counts, processed = process_video(
                    model=model,
                    video_path=temp_path,
                    conf=conf,
                    frame_stride=int(frame_stride),
                    max_frames=int(max_frames),
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
                sim_res = run_comparison_sumo(
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
                sim_backend = "sumo"
                st.success("Simulasi menggunakan SUMO/TraCI.")
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

        st.subheader("Perbandingan Fixed-Time vs Fuzzy")
        st.dataframe(pd.DataFrame(compare_rows), use_container_width=True)
        st.caption("Durasi merah dihitung sebagai lama sebuah arah berada di kondisi non-hijau sebelum mendapat hijau lagi.")

        fixed_df = pd.DataFrame(sim_res["fixed"]["timeline"])[["step", "queue_total"]].rename(columns={"queue_total": "Fixed"})
        fuzzy_df = pd.DataFrame(sim_res["fuzzy"]["timeline"])[["step", "queue_total"]].rename(columns={"queue_total": "Fuzzy"})
        chart_df = fixed_df.merge(fuzzy_df, on="step", how="inner").set_index("step")
        st.line_chart(chart_df)
        
        render_cycle_analysis(sim_res["fixed"]["timeline"], sim_res["fuzzy"]["timeline"], simpang, key_suffix="live")

        st.subheader("Rencana Fase Lampu (Conflict-aware)")
        for i, phase in enumerate(sim_res["fuzzy"]["phase_plan"], start=1):
            green_dirs = phase.get("green_dirs", phase.get("dirs", []))
            notes = phase.get("notes", "-")
            st.markdown(f"{i}. **{phase.get('name', f'Phase {i}')}** | Green: `{', '.join(green_dirs)}` | {notes}")


if __name__ == "__main__":
    main()
