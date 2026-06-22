import os
import sys
import json
import urllib.request
import subprocess
import datetime

API_URL = "https://balisatudata.baliprov.go.id/api/v1/report-cctv"

def get_cctv_list():
    try:
        req = urllib.request.Request(
            API_URL, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            return data.get("data", {})
    except Exception as e:
        print(f"Error fetching CCTV list: {e}")
        return {}

def list_all_cctvs(cctvs):
    print(f"\nTotal CCTV tersedia: {len(cctvs)}")
    print(f"{'No.':<5} | {'ID CCTV':<45} | {'Nama CCTV':<45}")
    print("-" * 105)
    for idx, (cid, info) in enumerate(cctvs.items(), 1):
        ch_id = info.get("ch_id") or info.get("streaming_url", "").split("id=")[-1]
        name = info.get("ch_name", "Unknown")
        print(f"{idx:<5} | {ch_id:<45} | {name:<45}")

def search_cctvs(cctvs, keyword):
    keyword = keyword.lower()
    results = []
    for cid, info in cctvs.items():
        ch_id = info.get("ch_id") or info.get("streaming_url", "").split("id=")[-1]
        name = info.get("ch_name", "Unknown")
        if keyword in str(ch_id).lower() or keyword in name.lower():
            results.append((ch_id, name))
    return results

def record_stream(ch_id, name, duration_minutes=30):
    duration_seconds = duration_minutes * 60
    stream_url = f"https://transcode.baliprov.go.id/cctv/{ch_id}/index.m3u8"
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = "rekaman_cctv"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    output_filename = os.path.join(output_dir, f"{ch_id}_{timestamp}.mp4")
    err_log = os.path.join(output_dir, f"{ch_id}_{timestamp}.mp4.err.log")
    out_log = os.path.join(output_dir, f"{ch_id}_{timestamp}.mp4.out.log")
    
    print(f"\n==========================================")
    print(f"Memulai perekaman CCTV:")
    print(f"Nama       : {name}")
    print(f"ID CCTV    : {ch_id}")
    print(f"Stream URL : {stream_url}")
    print(f"Durasi     : {duration_minutes} menit ({duration_seconds} detik)")
    print(f"Output     : {output_filename}")
    print(f"Log Error  : {err_log}")
    print(f"==========================================\n")
    
    # ffmpeg command
    cmd = [
        "ffmpeg",
        "-y",
        "-i", stream_url,
        "-c", "copy",
        "-t", str(duration_seconds),
        output_filename
    ]
    
    try:
        with open(out_log, "w", encoding="utf-8") as out_f, open(err_log, "w", encoding="utf-8") as err_f:
            process = subprocess.Popen(cmd, stdout=out_f, stderr=err_f)
            print(f"Proses perekaman berjalan di background dengan PID: {process.pid}")
            print("Perekaman sedang berlangsung... Anda bisa memantau log error atau menunggu.")
            process.wait()
            
        if process.returncode == 0:
            print(f"\nPerekaman selesai dengan sukses! Video disimpan sebagai: {output_filename}")
        else:
            print(f"\nPerekaman berhenti dengan kode error: {process.returncode}")
            print(f"Silakan periksa file log error: {err_log}")
    except FileNotFoundError:
        print("\n[X] Error: 'ffmpeg' tidak ditemukan pada sistem.")
        print("Pastikan FFmpeg terinstall dan terdaftar di variabel PATH sistem Anda.")
    except Exception as e:
        print(f"\nTerjadi kesalahan: {e}")

if __name__ == "__main__":
    cctvs = get_cctv_list()
    if not cctvs:
        print("Gagal memuat daftar CCTV. Keluar.")
        sys.exit(1)
        
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--list":
            list_all_cctvs(cctvs)
        elif arg == "--search" and len(sys.argv) > 2:
            keyword = sys.argv[2]
            results = search_cctvs(cctvs, keyword)
            print(f"\nHasil pencarian untuk '{keyword}':")
            for ch_id, name in results:
                print(f"- ID: {ch_id} | Nama: {name}")
        elif arg == "--record" and len(sys.argv) > 2:
            ch_id = sys.argv[2]
            # Find name
            name = "Unknown CCTV"
            for cid, info in cctvs.items():
                cur_id = info.get("ch_id") or info.get("streaming_url", "").split("id=")[-1]
                if cur_id == ch_id:
                    name = info.get("ch_name", "Unknown")
                    break
            
            duration = 30
            if len(sys.argv) > 3:
                try:
                    duration = int(sys.argv[3])
                except ValueError:
                    pass
            record_stream(ch_id, name, duration)
        else:
            print("Penggunaan:")
            print("  python record_cctv.py --list")
            print("  python record_cctv.py --search <kata_kunci>")
            print("  python record_cctv.py --record <id_cctv> [durasi_menit]")
    else:
        # Interactive mode
        print("=== CCTV Recorder Bali Satu Data ===")
        print("1. Tampilkan semua CCTV")
        print("2. Cari CCTV")
        print("3. Rekam CCTV")
        pilihan = input("Pilih menu (1-3): ").strip()
        
        if pilihan == "1":
            list_all_cctvs(cctvs)
        elif pilihan == "2":
            kw = input("Masukkan kata kunci pencarian (misal: 'unud', 'kedonganan'): ").strip()
            results = search_cctvs(cctvs, kw)
            print(f"\nHasil pencarian untuk '{kw}':")
            for ch_id, name in results:
                print(f"- ID: {ch_id} | Nama: {name}")
        elif pilihan == "3":
            ch_id = input("Masukkan ID CCTV (misal: 'simpang-kedonganan'): ").strip()
            # Find name
            name = "Unknown CCTV"
            for cid, info in cctvs.items():
                cur_id = info.get("ch_id") or info.get("streaming_url", "").split("id=")[-1]
                if cur_id == ch_id:
                    name = info.get("ch_name", "Unknown")
                    break
            dur_input = input("Masukkan durasi perekaman dalam menit (default: 30): ").strip()
            duration = 30
            if dur_input:
                try:
                    duration = int(dur_input)
                except ValueError:
                    print("Input tidak valid, menggunakan durasi default 30 menit.")
            record_stream(ch_id, name, duration)
