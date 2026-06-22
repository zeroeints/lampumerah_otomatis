"""
=============================================================================
analyze_results.py — Analisis Hasil Simulasi & Grafik Perbandingan
=============================================================================
Jalankan setelah simulasi selesai:
    python analyze_results.py
    python analyze_results.py --log output/sim_log_20260101_120000.json
=============================================================================
"""
import json, glob, argparse
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from pathlib import Path

CLASS_COLORS = {"N":"#00e5ff","S":"#7c3aed","E":"#f59e0b","W":"#ec4899"}
DARK_BG      = "#0a0e1a"
PANEL_BG     = "#111827"
TEXT_COLOR   = "#e2e8f0"
MUTED_COLOR  = "#94a3b8"
GRID_COLOR   = "#1e2d45"


def load_log(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_latest_log() -> str:
    logs = sorted(glob.glob("output/sim_log_*.json"))
    if not logs:
        raise FileNotFoundError("Tidak ada log ditemukan di folder output/")
    print(f"  [*] Menggunakan log terbaru: {logs[-1]}")
    return logs[-1]


def plot_full_report(data: dict, out_path: str = "output/laporan_simulasi.png"):
    """Buat laporan grafik lengkap 6 panel."""
    records  = data["records"]
    summary  = data["summary"]
    metadata = data.get("metadata", {})

    steps    = [r["step"]   for r in records]
    waits    = [r["wait"]   for r in records]
    queues   = [r["queue"]  for r in records]
    totals   = [r["total"]  for r in records]
    ns_durs  = [r["ns_dur"] for r in records]
    ew_durs  = [r["ew_dur"] for r in records]
    lats     = [r["lat_ms"] for r in records]

    N_lane   = [r["N"]      for r in records]
    S_lane   = [r["S"]      for r in records]
    E_lane   = [r["E"]      for r in records]
    W_lane   = [r["W"]      for r in records]

    fig = plt.figure(figsize=(18, 11), facecolor=DARK_BG)
    fig.suptitle(
        f"Laporan Simulasi — Sistem Pengendalian Lampu Lalu Lintas Adaptif\n"
        f"YOLOv11 + Logika Fuzzy | {metadata.get('mahasiswa','')} | "
        f"NIM. {metadata.get('nim','')} | {metadata.get('institusi','')} 2026",
        color=TEXT_COLOR, fontsize=11, fontweight="bold", y=0.98,
    )

    gs  = gridspec.GridSpec(3, 2, figure=fig, hspace=0.42, wspace=0.35)
    axs = [
        fig.add_subplot(gs[0, 0]),    # 0: Waktu tunggu adaptif
        fig.add_subplot(gs[0, 1]),    # 1: Kendaraan per lajur
        fig.add_subplot(gs[1, 0]),    # 2: Durasi hijau
        fig.add_subplot(gs[1, 1]),    # 3: Panjang antrean
        fig.add_subplot(gs[2, 0]),    # 4: Latency
        fig.add_subplot(gs[2, 1]),    # 5: Ringkasan
    ]

    def style(ax, title, xlabel="Langkah Simulasi", ylabel=""):
        ax.set_facecolor(PANEL_BG)
        ax.set_title(title, color=TEXT_COLOR, fontsize=9, pad=4)
        ax.set_xlabel(xlabel, color=MUTED_COLOR, fontsize=7)
        if ylabel:
            ax.set_ylabel(ylabel, color=MUTED_COLOR, fontsize=7)
        ax.tick_params(colors=MUTED_COLOR, labelsize=7)
        ax.grid(True, alpha=0.12, color=GRID_COLOR)
        for sp in ax.spines.values():
            sp.set_edgecolor(GRID_COLOR)
        return ax

    # ── 0: Waktu Tunggu Adaptif ───────────────────────────
    style(axs[0], "Waktu Tunggu — Sistem Adaptif", ylabel="Detik")
    axs[0].plot(steps, waits, color="#00e5ff", lw=1.5, label="Adaptif (YOLO+Fuzzy)", alpha=0.9)
    if len(waits) > 20:
        ma = np.convolve(waits, np.ones(20)/20, mode="same")
        axs[0].plot(steps, ma, color="#ffffff", lw=1.0, linestyle="--", alpha=0.5, label="Moving Avg")
    axs[0].legend(fontsize=7, facecolor=PANEL_BG, labelcolor=TEXT_COLOR,
                  loc="upper right", framealpha=0.8)

    # ── 1: Kendaraan per lajur ─────────────────────────────
    style(axs[1], "Jumlah Kendaraan per Lajur (YOLOv11)", ylabel="Kendaraan")
    axs[1].plot(steps, N_lane, color="#00e5ff", lw=1, label="Utara (N)", alpha=0.85)
    axs[1].plot(steps, S_lane, color="#7c3aed", lw=1, label="Selatan (S)", alpha=0.85)
    axs[1].plot(steps, E_lane, color="#f59e0b", lw=1, label="Timur (E)", alpha=0.85)
    axs[1].plot(steps, W_lane, color="#ec4899", lw=1, label="Barat (W)", alpha=0.85)
    axs[1].legend(fontsize=7, facecolor=PANEL_BG, labelcolor=TEXT_COLOR,
                  ncol=4, loc="upper right", framealpha=0.8)

    # ── 2: Durasi hijau adaptif ────────────────────────────
    style(axs[2], "Durasi Hijau Adaptif", ylabel="Detik")
    axs[2].plot(steps, ns_durs, color="#00ff88", lw=1.2, label="NS Hijau")
    axs[2].plot(steps, ew_durs, color="#ff6b6b", lw=1.2, label="EW Hijau", linestyle="--")
    axs[2].axhline(30, color="#ffffff", lw=0.7, linestyle=":", alpha=0.4, label="Referensi 30s")
    axs[2].set_ylim(5, 65)
    axs[2].legend(fontsize=7, facecolor=PANEL_BG, labelcolor=TEXT_COLOR, framealpha=0.8)

    # ── 3: Panjang antrean ─────────────────────────────────
    style(axs[3], "Panjang Antrean", ylabel="Kendaraan")
    axs[3].fill_between(steps, 0, queues, alpha=0.25, color="#f59e0b")
    axs[3].plot(steps, queues, color="#f59e0b", lw=1.2)
    if len(queues) > 20:
        ma = np.convolve(queues, np.ones(20)/20, mode="same")
        axs[3].plot(steps, ma, color="#ffffff", lw=1.0, linestyle="--", alpha=0.6)

    # ── 4: Latency YOLO ────────────────────────────────────
    style(axs[4], "Latency Inferensi YOLOv11", ylabel="ms")
    lat_valid = [l for l in lats if l > 0]
    lat_steps = [s for s, l in zip(steps, lats) if l > 0]
    if lat_valid:
        axs[4].scatter(lat_steps, lat_valid, color="#00e5ff", s=4, alpha=0.5)
        avg_lat = np.mean(lat_valid)
        axs[4].axhline(avg_lat, color="#ff6b6b", lw=1.2, linestyle="--",
                       label=f"Avg={avg_lat:.1f}ms")
        axs[4].axhline(100, color="#f59e0b", lw=0.8, linestyle=":", alpha=0.6,
                       label="Target <100ms")
        axs[4].legend(fontsize=7, facecolor=PANEL_BG, labelcolor=TEXT_COLOR, framealpha=0.8)

    # ── 5: Tabel ringkasan ─────────────────────────────────
    axs[5].axis("off")
    axs[5].set_facecolor(PANEL_BG)
    txt = (
        f"  RINGKASAN HASIL\n"
        f"  {'─'*28}\n"
        f"  Total langkah : {summary.get('total_steps',0):,}\n\n"
        f"  SISTEM ADAPTIF:\n"
        f"  Avg tunggu  : {summary.get('avg_wait_s',0):.2f} s\n"
        f"  Max tunggu  : {summary.get('max_wait_s',0):.2f} s\n"
        f"  Avg antrean : {summary.get('avg_queue',0):.1f} kend\n"
        f"  Avg latency : {summary.get('avg_lat_ms',0):.1f} ms\n\n"
        f"  BASELINE FIXED-TIME:\n"
        f"  (Tidak tersedia — jalankan\n"
        f"   simulasi terpisah untuk\n"
        f"   perbandingan yang valid)\n"
        f"  {'─'*28}\n"
        f"  Model: YOLOv11 + Fuzzy\n"
        f"  Defuzzifikasi: Centroid"
    )
    axs[5].text(0.03, 0.97, txt, transform=axs[5].transAxes, fontsize=8,
                verticalalignment="top", fontfamily="monospace", color=TEXT_COLOR,
                bbox=dict(facecolor="#060b14", edgecolor=GRID_COLOR,
                          boxstyle="round,pad=0.5", alpha=0.9))

    # Simpan
    Path(out_path).parent.mkdir(exist_ok=True)
    plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=DARK_BG)
    plt.close()
    print(f"  [✓] Grafik disimpan: {out_path}")
    return out_path


def print_summary_table(data: dict):
    """Cetak tabel ringkasan ke konsol."""
    s  = data["summary"]
    md = data.get("metadata", {})

    print("\n" + "═" * 58)
    print("  HASIL SIMULASI — SISTEM LAMPU LALU LINTAS ADAPTIF")
    print(f"  {md.get('mahasiswa','')} | NIM. {md.get('nim','')}")
    print("═" * 58)
    print(f"\n  {'METRIK':<30} {'ADAPTIF':>10}")
    print("  " + "─" * 42)

    rows = [
        ("Avg Waktu Tunggu (s)",  s.get("avg_wait_s", 0)),
        ("Max Waktu Tunggu (s)",  s.get("max_wait_s", 0)),
        ("Avg Panjang Antrean",   s.get("avg_queue", 0)),
        ("Max Panjang Antrean",   s.get("max_queue", 0)),
        ("Avg Latency YOLO (ms)", s.get("avg_lat_ms", 0)),
    ]
    for name, adap in rows:
        print(f"  {name:<30} {adap:>10.2f}")

    print("  " + "─" * 42)
    print(f"\n  [!] Baseline fixed-time tidak tersedia.")
    print(f"      Jalankan simulasi terpisah dengan fixed-time untuk perbandingan.")
    print(f"  Total langkah simulasi  : {s.get('total_steps',0):,}")
    print("═" * 58)


def main():
    p = argparse.ArgumentParser(description="Analisis hasil simulasi")
    p.add_argument("--log", default=None, help="Path ke file log JSON")
    args = p.parse_args()

    log_path = args.log or find_latest_log()
    data     = load_log(log_path)

    print_summary_table(data)

    ts       = Path(log_path).stem.replace("sim_log_", "")
    out_path = f"output/laporan_{ts}.png"
    plot_full_report(data, out_path)

    print(f"\n  File log    : {log_path}")
    print(f"  Grafik      : {out_path}")
    print("\n  Selesai! Buka grafik untuk melihat laporan visual lengkap.")


if __name__ == "__main__":
    main()
