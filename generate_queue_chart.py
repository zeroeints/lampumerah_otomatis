import json
import matplotlib.pyplot as plt
import os

def main():
    log_path = "output/sim_log_20260621_075137.json"
    if not os.path.exists(log_path):
        print(f"[!] Log file {log_path} not found.")
        return
        
    print(f"[+] Loading simulation logs from {log_path}...")
    with open(log_path, 'r') as f:
        data = json.load(f)
        
    fixed_timeline = data.get('fixed_timeline', [])
    fuzzy_timeline = data.get('fuzzy_timeline', [])
    
    if not fixed_timeline or not fuzzy_timeline:
        print("[!] Timeline data is empty in JSON.")
        return
        
    print(f"[+] Extracted fixed timeline ({len(fixed_timeline)} steps) and fuzzy timeline ({len(fuzzy_timeline)} steps).")
    
    fixed_q = [t.get('queue_total', 0.0) for t in fixed_timeline]
    fuzzy_q = [t.get('queue_total', 0.0) for t in fuzzy_timeline]
    
    # Generate the Line Chart
    plt.figure(figsize=(10, 5), dpi=300)
    plt.rcParams['font.family'] = 'sans-serif'
    
    plt.plot(fixed_q, label='Fixed-Time Control (Konvensional)', color='#d62728', linewidth=1.2, alpha=0.8)
    plt.plot(fuzzy_q, label='YOLOv11s + Logika Fuzzy (Adaptif)', color='#1f77b4', linewidth=1.2, alpha=0.9)
    
    plt.xlabel('Waktu Langkah Simulasi (Detik / Steps)', fontsize=11, fontweight='bold')
    plt.ylabel('Total Panjang Antrean Kendaraan (Unit / Kendaraan)', fontsize=11, fontweight='bold')
    plt.title('Grafik Perbandingan Panjang Antrean Kontinu Persimpangan\n(Fixed-Time vs Adaptif Fuzzy)', fontsize=12, fontweight='bold', pad=15)
    
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.legend(loc='upper right', fontsize=10, frameon=True, facecolor='white', edgecolor='gray')
    
    # Set axis limits
    plt.xlim(0, max(len(fixed_q), len(fuzzy_q)))
    plt.ylim(0, max(max(fixed_q), max(fuzzy_q)) + 5)
    
    plt.tight_layout()
    chart_path = "output/antrean_kontinu_komparasi.png"
    plt.savefig(chart_path)
    plt.close()
    print(f"[OK] Successfully generated and saved line chart to: {chart_path}")

if __name__ == "__main__":
    main()
