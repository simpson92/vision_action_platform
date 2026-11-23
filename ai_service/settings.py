"""AI 추론 서버 설정.

값은 환경변수(.env)로 바꿀 수 있고, 없으면 6~8일차 설정(day07_realtime.json,
day08_multi_person.json, project.json)과 같은 기본값을 사용합니다.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _env_float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, "1" if default else "0").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    model_dir: Path
    pose_model: str
    image_size: int
    person_confidence: float
    tracker: str
    # 6일차 학습 조건: Clip 안의 유효 Frame이 10개 미만이면 Sequence를 만들지 않음
    min_valid_frames: int
    # 판단 불확실 기준. 7일차 기준 0.55는 이 모델(학습 6 clip)에서 항상 UNKNOWN이 되므로
    # 1등 확률과 1·2등 차이(margin)를 함께 보고, 값은 S02(검증용 사람) 영상으로 맞춤
    confidence_threshold: float
    margin_threshold: float
    # 전체 구간 예측에 섞을 짧은 Window 길이·간격 (S02 검증 영상으로 2초·0.5초 선택)
    window_seconds: float
    window_stride_seconds: float
    # 낮은 Confidence 관절을 같은 사람의 앞뒤 Frame 값으로 보간 (Puchała 2023 아이디어)
    keypoint_interpolation: bool
    keypoint_min_confidence: float
    max_upload_mb: int


def load_settings() -> Settings:
    project = json.loads((BASE_DIR / "project.json").read_text(encoding="utf-8"))
    model_dir = Path(os.getenv("MODEL_DIR", BASE_DIR / "models"))
    return Settings(
        model_dir=model_dir,
        pose_model=os.getenv("POSE_MODEL", project.get("pose_model", "yolo11n-pose.pt")),
        image_size=_env_int("POSE_IMAGE_SIZE", project.get("image_size", 640)),
        person_confidence=_env_float("PERSON_CONFIDENCE", project.get("person_confidence", 0.25)),
        tracker=os.getenv("POSE_TRACKER", "bytetrack.yaml"),
        min_valid_frames=_env_int("MIN_VALID_FRAMES", 10),
        confidence_threshold=_env_float("CONFIDENCE_THRESHOLD", 0.20),
        margin_threshold=_env_float("MARGIN_THRESHOLD", 0.03),
        window_seconds=_env_float("WINDOW_SECONDS", 2.0),
        window_stride_seconds=_env_float("WINDOW_STRIDE_SECONDS", 0.5),
        keypoint_interpolation=_env_bool("KEYPOINT_INTERPOLATION", True),
        keypoint_min_confidence=_env_float("KEYPOINT_MIN_CONFIDENCE", 0.30),
        max_upload_mb=_env_int("MAX_UPLOAD_MB", 50),
    )
