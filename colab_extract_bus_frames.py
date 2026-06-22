"""
Google Colab helper script:
- Read a video file
- Detect buses on each frame with YOLO
- Save full frames containing at least one bus as images for a dataset

Quick Colab usage:
1. !pip install -q ultralytics opencv-python-headless
2. Upload this file and your video/model to Colab
3. Run:

from colab_extract_bus_frames import extract_bus_frames

extract_bus_frames(
    video_path="/content/simpang-kedonganan_20260605_084648.mkv",
    output_dir="/content/bus_dataset_frames",
    model_path="yolov8n.pt",  # or "/content/best.pt"
    conf_threshold=0.30,
    frame_stride=3,
    min_gap_seconds=0.5,
    save_annotated=True,
)
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import cv2
from ultralytics import YOLO


def extract_bus_frames(
    video_path: str,
    output_dir: str,
    model_path: str = "yolov8n.pt",
    target_class_name: str = "bus",
    conf_threshold: float = 0.30,
    frame_stride: int = 1,
    min_gap_seconds: float = 0.0,
    save_annotated: bool = False,
) -> Dict[str, float]:
    """
    Save full frames as images when at least one bus is detected.

    Args:
        video_path: Path to input video.
        output_dir: Folder where extracted images will be saved.
        model_path: YOLO model path. Can be a COCO model or your own model.
        target_class_name: Class name to collect, default is "bus".
        conf_threshold: Minimum confidence score for bus detections.
        frame_stride: Process every Nth frame to reduce runtime and duplicates.
        min_gap_seconds: Minimum time gap between saved frames.
        save_annotated: If True, also save annotated preview images.
    """
    video_file = Path(video_path)
    if not video_file.exists():
        raise FileNotFoundError(f"Video not found: {video_file}")

    output_root = Path(output_dir)
    raw_dir = output_root / "raw_frames"
    annotated_dir = output_root / "annotated_frames"
    raw_dir.mkdir(parents=True, exist_ok=True)
    if save_annotated:
        annotated_dir.mkdir(parents=True, exist_ok=True)

    model = YOLO(model_path)
    name_to_id = {str(name).lower(): idx for idx, name in model.names.items()}
    target_class_id = name_to_id.get(target_class_name.lower())
    if target_class_id is None:
        raise ValueError(
            f"Class '{target_class_name}' not found in model labels: "
            f"{list(model.names.values())}"
        )

    cap = cv2.VideoCapture(str(video_file))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_file}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    if fps <= 0:
        fps = 25.0

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    frame_index = 0
    saved_count = 0
    last_saved_time = -1e9

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        frame_index += 1
        if frame_stride > 1 and (frame_index % frame_stride) != 0:
            continue

        timestamp_sec = frame_index / fps
        if timestamp_sec - last_saved_time < min_gap_seconds:
            continue

        results = model.predict(
            source=frame,
            conf=conf_threshold,
            verbose=False,
        )
        result = results[0]

        bus_boxes: List[List[float]] = []
        if result.boxes is not None and len(result.boxes) > 0:
            for box in result.boxes:
                class_id = int(box.cls[0].item())
                confidence = float(box.conf[0].item())
                if class_id == target_class_id and confidence >= conf_threshold:
                    xyxy = box.xyxy[0].tolist()
                    bus_boxes.append(xyxy)

        if not bus_boxes:
            continue

        file_stem = f"frame_{frame_index:06d}_t_{timestamp_sec:08.2f}s_bus_{len(bus_boxes)}"
        raw_path = raw_dir / f"{file_stem}.jpg"
        cv2.imwrite(str(raw_path), frame)

        if save_annotated:
            annotated = frame.copy()
            for xyxy in bus_boxes:
                x1, y1, x2, y2 = [int(v) for v in xyxy]
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(
                    annotated,
                    target_class_name,
                    (x1, max(20, y1 - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 255, 0),
                    2,
                    cv2.LINE_AA,
                )
            annotated_path = annotated_dir / f"{file_stem}.jpg"
            cv2.imwrite(str(annotated_path), annotated)

        saved_count += 1
        last_saved_time = timestamp_sec

        if saved_count % 25 == 0:
            print(
                f"Saved {saved_count} frames "
                f"(processed frame {frame_index}/{total_frames or '?'})"
            )

    cap.release()

    summary = {
        "saved_frames": saved_count,
        "processed_frames": frame_index,
        "fps": fps,
        "video_seconds": frame_index / fps if fps else 0.0,
    }
    print("Done:", summary)
    return summary


if __name__ == "__main__":
    # Example local run. Edit these paths if you want to run the script directly.
    extract_bus_frames(
        video_path="simpang-kedonganan_20260605_084648.mkv",
        output_dir="bus_dataset_frames",
        model_path="yolov8n.pt",
        target_class_name="bus",
        conf_threshold=0.30,
        frame_stride=3,
        min_gap_seconds=0.5,
        save_annotated=True,
    )
