import logging
import os
import sys
from typing import Dict, List, Any, Optional
from datetime import datetime

from fastapi import FastAPI, BackgroundTasks, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Ensure local imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from simulation_db import (
    SimulationDatabase,
    SQLALCHEMY_AVAILABLE,
    is_database_enabled,
    get_database_url
)

if SQLALCHEMY_AVAILABLE:
    from simulation_db import (
        SimulationRun,
        PhaseEvent,
        SimulationStepMetric,
        DirectionStepMetric,
        DirectionRunStat
    )
    from sqlalchemy.orm import Session
else:
    SimulationRun = None
    PhaseEvent = None
    SimulationStepMetric = None
    DirectionStepMetric = None
    DirectionRunStat = None

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FastAPI")

app = FastAPI(
    title="Sistem Pengendalian Lampu Lalu Lintas Adaptif API",
    description="Backend API menggunakan FastAPI untuk mengendalikan simulasi lalu lintas SUMO dan menganalisis hasil deteksi YOLOv11 + Logika Fuzzy.",
    version="1.0.0"
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = SimulationDatabase()

# --- PYDANTIC SCHEMAS ---

class SimulationRequest(BaseModel):
    sumo_cfg: str = Field(default="sumo_config/intersection.sumocfg", description="Path to .sumocfg file")
    tl_id: str = Field(default="J_center", description="Traffic light ID in SUMO network")
    intersection_type: str = Field(default="Perempatan", description="Type of intersection (e.g., Perempatan, Pertigaan)")
    weighted_by_dir: Dict[str, float] = Field(
        default={"Utara": 1.0, "Selatan": 1.0, "Timur": 1.0, "Barat": 1.0},
        description="Weights of traffic density per direction"
    )
    duration_steps: int = Field(default=1800, description="Simulation steps/seconds")
    min_green: int = Field(default=10, description="Minimum green light duration in seconds")
    max_green: int = Field(default=60, description="Maximum green light duration in seconds")
    yellow: int = Field(default=3, description="Yellow light duration in seconds")
    all_red: int = Field(default=1, description="All red light duration in seconds")
    use_gui: bool = Field(default=False, description="Run SUMO with GUI (sumo-gui)")
    custom_fourway_logic: bool = Field(default=True, description="Use customized 4-way conflict-free logic")

class KPIOut(BaseModel):
    avg_wait_s: Optional[float] = None
    avg_red_s: Optional[float] = None
    max_red_s: Optional[float] = None
    max_queue: Optional[float] = None
    avg_queue: Optional[float] = None
    throughput_per_min: Optional[float] = None
    density_index: Optional[float] = None
    phase_fairness_gap: Optional[float] = None
    total_served: Optional[float] = None

class SimulationRunOut(BaseModel):
    id: int
    comparison_group_id: Optional[str]
    engine: str
    controller_mode: str
    status: str
    intersection_type: str
    sumo_cfg: Optional[str]
    tl_id: Optional[str]
    duration_steps: int
    started_at: datetime
    completed_at: Optional[datetime]
    avg_wait_s: Optional[float]
    total_served: Optional[float]
    error_message: Optional[str]

    class Config:
        from_attributes = True

# --- BACKGROUND TASK RUNNER ---

def run_simulation_in_background(req_dict: dict):
    logger.info(f"Memulai simulasi di background: {req_dict}")
    try:
        from sumo_simulation import run_comparison_sumo
        result = run_comparison_sumo(
            sumo_cfg=req_dict["sumo_cfg"],
            tl_id=req_dict["tl_id"],
            intersection_type=req_dict["intersection_type"],
            weighted_by_dir=req_dict["weighted_by_dir"],
            duration_steps=req_dict["duration_steps"],
            min_green=req_dict["min_green"],
            max_green=req_dict["max_green"],
            yellow=req_dict["yellow"],
            all_red=req_dict["all_red"],
            use_gui=req_dict["use_gui"],
            custom_fourway_logic=req_dict["custom_fourway_logic"]
        )
        logger.info("Simulsi background selesai dengan sukses.")
    except Exception as e:
        logger.error(f"Simulasi background gagal: {e}")

# --- API ENDPOINTS ---

@app.get("/")
def get_root():
    return {
        "status": "online",
        "message": "Sistem Pengendalian Lampu Lalu Lintas Adaptif API",
        "database_connected": db.enabled,
        "database_url": get_database_url() if db.enabled else "None",
        "sumo_home": os.environ.get("SUMO_HOME", "Not Set")
    }

@app.post("/api/simulate")
def trigger_simulation(payload: SimulationRequest, background_tasks: BackgroundTasks):
    """
    Memicu jalannya simulasi SUMO (Fixed-Time vs Fuzzy) secara asinkron di background.
    """
    if not db.enabled:
        raise HTTPException(
            status_code=503,
            detail="Database MySQL tidak aktif atau SQLAlchemy tidak terinstall. Simulasi tidak dapat dicatat."
        )
    
    # Cek ketersediaan SUMO
    if not os.environ.get("SUMO_HOME"):
        raise HTTPException(
            status_code=500,
            detail="Environment variable SUMO_HOME tidak diset pada server ini."
        )

    req_dict = payload.model_dump()
    background_tasks.add_task(run_simulation_in_background, req_dict)
    
    return {
        "message": "Simulasi berhasil dijadwalkan di background.",
        "parameters": req_dict
    }

@app.get("/api/runs", response_model=List[SimulationRunOut])
def list_runs(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    """
    Mengambil daftar riwayat jalannya simulasi yang tersimpan di MySQL.
    """
    if not db.enabled or db._session_factory is None:
        raise HTTPException(status_code=503, detail="Koneksi database tidak tersedia.")
    
    session = db._session_factory()
    try:
        runs = session.query(SimulationRun).order_by(SimulationRun.id.desc()).offset(offset).limit(limit).all()
        return runs
    except Exception as e:
        logger.error(f"Gagal mengambil daftar runs: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        session.close()

@app.get("/api/runs/{run_id}")
def get_run_details(run_id: int):
    """
    Mengambil detail metrik performa (KPI) serta fase lampu untuk run_id tertentu.
    """
    if not db.enabled or db._session_factory is None:
        raise HTTPException(status_code=503, detail="Koneksi database tidak tersedia.")
    
    session = db._session_factory()
    try:
        run = session.query(SimulationRun).filter(SimulationRun.id == run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Simulation run tidak ditemukan.")
        
        # Serialize model data ke dictionary
        run_data = {
            "id": run.id,
            "comparison_group_id": run.comparison_group_id,
            "engine": run.engine,
            "controller_mode": run.controller_mode,
            "status": run.status,
            "intersection_type": run.intersection_type,
            "duration_steps": run.duration_steps,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "error_message": run.error_message,
            "kpis": {
                "avg_wait_s": run.avg_wait_s,
                "avg_red_s": run.avg_red_s,
                "max_red_s": run.max_red_s,
                "max_queue": run.max_queue,
                "avg_queue": run.avg_queue,
                "throughput_per_min": run.throughput_per_min,
                "density_index": run.density_index,
                "phase_fairness_gap": run.phase_fairness_gap,
                "total_served": run.total_served
            }
        }
        return run_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Gagal mengambil detail run: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        session.close()

@app.get("/api/runs/{run_id}/step-metrics")
def get_run_step_metrics(run_id: int):
    """
    Mengambil statistik langkah demi langkah (panjang antrean, waktu tunggu) untuk diplot di grafik dashboard.
    """
    if not db.enabled or db._session_factory is None:
        raise HTTPException(status_code=503, detail="Koneksi database tidak tersedia.")
    
    session = db._session_factory()
    try:
        run = session.query(SimulationRun).filter(SimulationRun.id == run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Simulation run tidak ditemukan.")
        
        metrics = (
            session.query(SimulationStepMetric)
            .filter(SimulationStepMetric.run_id == run_id)
            .order_by(SimulationStepMetric.step_index.asc())
            .all()
        )
        
        result = []
        for m in metrics:
            result.append({
                "step_index": m.step_index,
                "phase_name": m.phase_name,
                "phase_index": m.phase_index,
                "status": m.status,
                "green_time": m.green_time,
                "queue_total": m.queue_total,
                "avg_wait_s": m.avg_wait_s,
                "phase_queue": m.phase_queue,
                "phase_score": m.phase_score
            })
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Gagal mengambil metrik langkah: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        session.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app_fastapi:app", host="0.0.0.0", port=8000, reload=True)
