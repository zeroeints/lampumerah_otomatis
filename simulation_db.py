import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from sqlalchemy import (
        JSON,
        Boolean,
        DateTime,
        Float,
        ForeignKey,
        Integer,
        String,
        Text,
        create_engine,
    )
    from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

    SQLALCHEMY_AVAILABLE = True
except Exception:
    SQLALCHEMY_AVAILABLE = False


DEFAULT_DB_URL = "mysql+pymysql://root@127.0.0.1:3306/traffic_simulation"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_database_url() -> str:
    return os.environ.get("TRAFFIC_SIM_DB_URL", DEFAULT_DB_URL)


def is_database_enabled() -> bool:
    raw = os.environ.get("TRAFFIC_SIM_DB_ENABLED", "").strip().lower()
    if raw:
        return raw not in {"0", "false", "no", "off"}
    return SQLALCHEMY_AVAILABLE


if SQLALCHEMY_AVAILABLE:
    class Base(DeclarativeBase):
        pass


    class SimulationRun(Base):
        __tablename__ = "simulation_runs"

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        comparison_group_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
        engine: Mapped[str] = mapped_column(String(32))
        controller_mode: Mapped[str] = mapped_column(String(16))
        status: Mapped[str] = mapped_column(String(16), default="pending")
        intersection_type: Mapped[str] = mapped_column(String(32))
        sumo_cfg: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
        tl_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
        resolved_tl_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
        use_gui: Mapped[bool] = mapped_column(Boolean, default=False)
        custom_fourway_logic: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
        duration_steps: Mapped[int] = mapped_column(Integer)
        min_green: Mapped[int] = mapped_column(Integer)
        max_green: Mapped[int] = mapped_column(Integer)
        yellow: Mapped[int] = mapped_column(Integer)
        all_red: Mapped[int] = mapped_column(Integer)
        weighted_by_dir: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
        phase_plan: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
        started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
        completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
        error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
        avg_wait_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
        avg_red_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
        max_red_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
        max_queue: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
        avg_queue: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
        throughput_per_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
        density_index: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
        phase_fairness_gap: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
        total_served: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

        phase_events: Mapped[List["PhaseEvent"]] = relationship(back_populates="run", cascade="all, delete-orphan")
        step_metrics: Mapped[List["SimulationStepMetric"]] = relationship(back_populates="run", cascade="all, delete-orphan")
        direction_step_metrics: Mapped[List["DirectionStepMetric"]] = relationship(back_populates="run", cascade="all, delete-orphan")
        direction_stats: Mapped[List["DirectionRunStat"]] = relationship(back_populates="run", cascade="all, delete-orphan")


    class PhaseEvent(Base):
        __tablename__ = "phase_events"

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        run_id: Mapped[int] = mapped_column(ForeignKey("simulation_runs.id"), index=True)
        step_index: Mapped[int] = mapped_column(Integer)
        event_type: Mapped[str] = mapped_column(String(32))
        phase_name: Mapped[str] = mapped_column(String(64))
        phase_index: Mapped[int] = mapped_column(Integer)
        stage: Mapped[str] = mapped_column(String(16))
        assigned_duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
        actual_duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
        reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
        directions: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

        run: Mapped["SimulationRun"] = relationship(back_populates="phase_events")


    class SimulationStepMetric(Base):
        __tablename__ = "simulation_step_metrics"

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        run_id: Mapped[int] = mapped_column(ForeignKey("simulation_runs.id"), index=True)
        step_index: Mapped[int] = mapped_column(Integer)
        phase_name: Mapped[str] = mapped_column(String(64))
        phase_index: Mapped[int] = mapped_column(Integer)
        status: Mapped[str] = mapped_column(String(16))
        green_time: Mapped[int] = mapped_column(Integer)
        queue_total: Mapped[float] = mapped_column(Float)
        avg_wait_s: Mapped[float] = mapped_column(Float)
        phase_queue: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
        phase_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

        run: Mapped["SimulationRun"] = relationship(back_populates="step_metrics")


    class DirectionStepMetric(Base):
        __tablename__ = "direction_step_metrics"

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        run_id: Mapped[int] = mapped_column(ForeignKey("simulation_runs.id"), index=True)
        step_index: Mapped[int] = mapped_column(Integer)
        direction: Mapped[str] = mapped_column(String(16))
        is_green: Mapped[bool] = mapped_column(Boolean)
        queue_count: Mapped[float] = mapped_column(Float)
        red_age: Mapped[int] = mapped_column(Integer)
        red_streak: Mapped[int] = mapped_column(Integer)
        pressure: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

        run: Mapped["SimulationRun"] = relationship(back_populates="direction_step_metrics")


    class DirectionRunStat(Base):
        __tablename__ = "direction_run_stats"

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        run_id: Mapped[int] = mapped_column(ForeignKey("simulation_runs.id"), index=True)
        direction: Mapped[str] = mapped_column(String(16))
        green_count: Mapped[int] = mapped_column(Integer)
        total_green_s: Mapped[float] = mapped_column(Float)
        avg_green_s: Mapped[float] = mapped_column(Float)
        max_green_s: Mapped[float] = mapped_column(Float)
        total_red_s: Mapped[float] = mapped_column(Float)
        avg_red_s: Mapped[float] = mapped_column(Float)
        max_red_s: Mapped[float] = mapped_column(Float)

        run: Mapped["SimulationRun"] = relationship(back_populates="direction_stats")
else:
    Base = object


_WARNED = False


def _warn_once(message: str) -> None:
    global _WARNED
    if not _WARNED:
        print(f"[DB] {message}")
        _WARNED = True


def _safe_json(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except Exception:
        return {"value": str(value)}


@dataclass
class RunTelemetry:
    metadata: Dict[str, Any]
    enabled: bool = False
    step_metrics: List[Dict[str, Any]] = field(default_factory=list)
    direction_step_metrics: List[Dict[str, Any]] = field(default_factory=list)
    phase_events: List[Dict[str, Any]] = field(default_factory=list)
    direction_stats: List[Dict[str, Any]] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None

    def record_step(
        self,
        *,
        step_index: int,
        phase_name: str,
        phase_index: int,
        status: str,
        green_time: int,
        queue_total: float,
        avg_wait_s: float,
        phase_queue: Optional[float],
        phase_score: Optional[float],
        direction_state: Dict[str, Dict[str, Any]],
    ) -> None:
        if not self.enabled:
            return
        self.step_metrics.append({
            "step_index": step_index,
            "phase_name": phase_name,
            "phase_index": phase_index,
            "status": status,
            "green_time": green_time,
            "queue_total": float(queue_total),
            "avg_wait_s": float(avg_wait_s),
            "phase_queue": None if phase_queue is None else float(phase_queue),
            "phase_score": None if phase_score is None else float(phase_score),
        })
        for direction, state in direction_state.items():
            self.direction_step_metrics.append({
                "step_index": step_index,
                "direction": direction,
                "is_green": bool(state.get("is_green", False)),
                "queue_count": float(state.get("queue_count", 0.0)),
                "red_age": int(state.get("red_age", 0)),
                "red_streak": int(state.get("red_streak", 0)),
                "pressure": None if state.get("pressure") is None else float(state["pressure"]),
            })

    def record_phase_event(
        self,
        *,
        step_index: int,
        event_type: str,
        phase_name: str,
        phase_index: int,
        stage: str,
        assigned_duration: Optional[int],
        actual_duration: Optional[int],
        reason: Optional[str],
        directions: List[str],
    ) -> None:
        if not self.enabled:
            return
        self.phase_events.append({
            "step_index": step_index,
            "event_type": event_type,
            "phase_name": phase_name,
            "phase_index": phase_index,
            "stage": stage,
            "assigned_duration": assigned_duration,
            "actual_duration": actual_duration,
            "reason": reason,
            "directions": _safe_json(directions),
        })

    def set_direction_stats(self, stats: List[Dict[str, Any]]) -> None:
        if self.enabled:
            self.direction_stats = stats

    def complete(self, summary: Dict[str, Any], error_message: Optional[str] = None) -> None:
        self.summary = summary
        self.error_message = error_message


@dataclass
class NullTelemetry:
    metadata: Dict[str, Any]
    enabled: bool = False

    def record_step(self, **_: Any) -> None:
        return

    def record_phase_event(self, **_: Any) -> None:
        return

    def set_direction_stats(self, stats: List[Dict[str, Any]]) -> None:
        return

    def complete(self, summary: Dict[str, Any], error_message: Optional[str] = None) -> None:
        return


class SimulationDatabase:
    def __init__(self):
        self.enabled = is_database_enabled() and SQLALCHEMY_AVAILABLE
        self._session_factory = None
        if self.enabled:
            engine = create_engine(get_database_url(), pool_pre_ping=True)
            self._session_factory = sessionmaker(bind=engine)
        elif not SQLALCHEMY_AVAILABLE:
            _warn_once("SQLAlchemy belum terpasang, pencatatan database dinonaktifkan.")

    def create_run(self, metadata: Dict[str, Any]) -> RunTelemetry | NullTelemetry:
        if not self.enabled or self._session_factory is None:
            if not SQLALCHEMY_AVAILABLE:
                _warn_once("SQLAlchemy belum tersedia, pencatatan database dinonaktifkan.")
            return NullTelemetry(metadata=metadata)
        return RunTelemetry(metadata=metadata, enabled=True)

    def persist(self, run: RunTelemetry | NullTelemetry) -> None:
        if not getattr(run, "enabled", False):
            return
        if self._session_factory is None:
            return
        session = self._session_factory()
        try:
            model = SimulationRun(
                comparison_group_id=run.metadata.get("comparison_group_id"),
                engine=run.metadata["engine"],
                controller_mode=run.metadata["controller_mode"],
                status="failed" if run.error_message else "completed",
                intersection_type=run.metadata["intersection_type"],
                sumo_cfg=run.metadata.get("sumo_cfg"),
                tl_id=run.metadata.get("tl_id"),
                resolved_tl_id=run.metadata.get("resolved_tl_id"),
                use_gui=bool(run.metadata.get("use_gui", False)),
                custom_fourway_logic=run.metadata.get("custom_fourway_logic"),
                duration_steps=int(run.metadata["duration_steps"]),
                min_green=int(run.metadata["min_green"]),
                max_green=int(run.metadata["max_green"]),
                yellow=int(run.metadata["yellow"]),
                all_red=int(run.metadata["all_red"]),
                weighted_by_dir=_safe_json(run.metadata.get("weighted_by_dir")),
                phase_plan=_safe_json(run.metadata.get("phase_plan")),
                started_at=run.metadata.get("started_at", utcnow()),
                completed_at=utcnow(),
                error_message=run.error_message,
                avg_wait_s=run.summary.get("avg_wait_s"),
                avg_red_s=run.summary.get("avg_red_s"),
                max_red_s=run.summary.get("max_red_s"),
                max_queue=run.summary.get("max_queue"),
                avg_queue=run.summary.get("avg_queue"),
                throughput_per_min=run.summary.get("throughput_per_min"),
                density_index=run.summary.get("density_index"),
                phase_fairness_gap=run.summary.get("phase_fairness_gap"),
                total_served=run.summary.get("total_served"),
            )
            session.add(model)
            session.flush()

            session.add_all([
                PhaseEvent(run_id=model.id, **event)
                for event in run.phase_events
            ])
            session.add_all([
                SimulationStepMetric(run_id=model.id, **row)
                for row in run.step_metrics
            ])
            session.add_all([
                DirectionStepMetric(run_id=model.id, **row)
                for row in run.direction_step_metrics
            ])
            session.add_all([
                DirectionRunStat(run_id=model.id, **row)
                for row in run.direction_stats
            ])
            session.commit()
        except Exception as exc:
            session.rollback()
            _warn_once(f"Gagal menyimpan telemetry ke database: {exc}")
        finally:
            session.close()

    def get_sumo_fixed_reference(
        self,
        *,
        intersection_type: str,
        duration_steps: int,
    ) -> Optional[Dict[str, Any]]:
        if not self.enabled or self._session_factory is None or not SQLALCHEMY_AVAILABLE:
            return None
        session = self._session_factory()
        try:
            run = (
                session.query(SimulationRun)
                .filter(
                    SimulationRun.engine == "sumo_traci",
                    SimulationRun.controller_mode == "fixed",
                    SimulationRun.status == "completed",
                    SimulationRun.intersection_type == intersection_type,
                    SimulationRun.duration_steps == int(duration_steps),
                )
                .order_by(SimulationRun.avg_wait_s.asc(), SimulationRun.id.desc())
                .first()
            )
            if run is None:
                return None

            green_events = (
                session.query(PhaseEvent)
                .filter(
                    PhaseEvent.run_id == run.id,
                    PhaseEvent.event_type == "green_start",
                )
                .all()
            )
            direction_stats = (
                session.query(DirectionRunStat)
                .filter(DirectionRunStat.run_id == run.id)
                .all()
            )

            ns_green = [
                float(row.avg_green_s)
                for row in direction_stats
                if row.direction in {"Utara", "Selatan"}
            ]
            ew_green = [
                float(row.avg_green_s)
                for row in direction_stats
                if row.direction in {"Timur", "Barat"}
            ]

            return {
                "run_id": int(run.id),
                "baseline_green": float(
                    sum(int(event.assigned_duration or 0) for event in green_events) / max(len(green_events), 1)
                ),
                "avg_red_s": None if run.avg_red_s is None else float(run.avg_red_s),
                "max_red_s": None if run.max_red_s is None else float(run.max_red_s),
                "avg_wait_s": None if run.avg_wait_s is None else float(run.avg_wait_s),
                "ns_avg_green_s": sum(ns_green) / max(len(ns_green), 1) if ns_green else None,
                "ew_avg_green_s": sum(ew_green) / max(len(ew_green), 1) if ew_green else None,
                "cycle_count_hint": len(green_events),
            }
        except Exception as exc:
            _warn_once(f"Gagal membaca calibration database: {exc}")
            return None
        finally:
            session.close()
