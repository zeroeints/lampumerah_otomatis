@echo off
REM ==========================================================
REM  SETUP_AND_RUN.BAT — Setup Otomatis Sistem (Windows)
REM  Skripsi: Mohammad Filla Firdaus | NIM. 2215354055
REM  Politeknik Negeri Bali | TRPL 2026
REM ==========================================================

echo.
echo  ====================================================
echo   SISTEM PENGENDALIAN LAMPU LALU LINTAS ADAPTIF
echo   YOLOv11 + Logika Fuzzy + SUMO TraCI
echo   Mohammad Filla Firdaus ^| NIM. 2215354055
echo  ====================================================
echo.

REM ── Cek Python ──────────────────────────────────────────
python --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo  [X] Python tidak ditemukan!
    echo      Download: https://www.python.org/downloads/
    pause & exit /b 1
)
echo  [OK] Python ditemukan

REM ── Set SUMO_HOME (sesuaikan path jika berbeda) ─────────
IF "%SUMO_HOME%"=="" (
    REM Coba path instalasi default SUMO Windows
    IF EXIST "C:\Program Files (x86)\Eclipse\Sumo" (
        SET "SUMO_HOME=C:\Program Files (x86)\Eclipse\Sumo"
        echo  [OK] SUMO_HOME otomatis diset.
    ) ELSE IF EXIST "C:\Sumo" (
        SET "SUMO_HOME=C:\Sumo"
        echo  [OK] SUMO_HOME otomatis diset.
    ) ELSE (
        echo  [!] SUMO_HOME belum diset!
        echo      Edit file ini dan set SUMO_HOME ke path instalasi SUMO Anda
        echo      Contoh: SET SUMO_HOME=C:\Program Files ^(x86^)\Eclipse\Sumo
        echo.
        echo      Download SUMO: https://sumo.dlr.de/docs/Downloads.php
    )
) ELSE (
    echo  [OK] SUMO_HOME = "%SUMO_HOME%"
)

REM ── Install dependensi Python ────────────────────────────
echo.
echo  [*] Menginstall dependensi Python...
pip install ultralytics scikit-fuzzy scipy fastapi uvicorn ^
    python-multipart opencv-python matplotlib numpy streamlit pandas -q

IF ERRORLEVEL 1 (
    echo  [X] Instalasi gagal! Periksa koneksi internet Anda.
    pause & exit /b 1
)
echo  [OK] Dependensi terinstall

REM ── Buat folder yang diperlukan ─────────────────────────
IF NOT EXIST "output" mkdir output
IF NOT EXIST "logs"   mkdir logs
echo  [OK] Folder output dan logs dibuat

REM ── Cek best.pt ─────────────────────────────────────────
IF NOT EXIST "best.pt" (
    echo.
    echo  [!] PERHATIAN: best.pt tidak ditemukan di folder ini!
    echo      Salin best.pt dari Google Drive ke: %CD%\best.pt
    echo.
) ELSE (
    echo  [OK] best.pt ditemukan
)

echo.
echo  ====================================================
echo   PILIH AKSI:
echo  ====================================================
echo   1. Test cepat (verifikasi integrasi tanpa SUMO)
echo   2. Jalankan simulasi penuh (dengan SUMO GUI)
echo   3. Jalankan simulasi tanpa GUI (lebih cepat)
echo   4. Analisis hasil simulasi terakhir
echo   5. Jalankan Dashboard Tampilan Visual (Streamlit GUI)
echo   6. Keluar
echo.
set /p choice="  Pilihan (1-6): "

IF "%choice%"=="1" (
    echo.
    echo  [*] Menjalankan test integrasi...
    python main_controller.py --test
    goto END
)

IF "%choice%"=="2" (
    echo.
    echo  [*] Menjalankan simulasi penuh dengan GUI...
    echo      [Tutup jendela SUMO atau tekan Ctrl+C untuk berhenti]
    echo.
    python main_controller.py --model best.pt --steps 3600
    goto ANALYZE
)

IF "%choice%"=="3" (
    echo.
    echo  [*] Menjalankan simulasi tanpa GUI [1 jam simulasi]...
    python main_controller.py --model best.pt --steps 3600 --nogui
    goto ANALYZE
)

IF "%choice%"=="4" (
    goto ANALYZE
)

IF "%choice%"=="5" (
    echo.
    echo  [*] Menjalankan Dashboard Streamlit GUI...
    echo      [Tekan Ctrl+C di cmd ini untuk menghentikan]
    echo.
    streamlit run app_yolo11_gui.py
    goto END
)

IF "%choice%"=="6" goto END

echo  [!] Pilihan tidak valid.
goto END

:ANALYZE
echo.
echo  [*] Membuat laporan analisis...
python analyze_results.py
echo.
echo  [OK] Laporan disimpan di folder output/

:END
echo.
echo  Selesai.
pause
