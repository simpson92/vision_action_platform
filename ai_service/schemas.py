"""FastAPI 요청·응답 형식 (Pydantic). Celery Worker와 합의한 API 계약입니다."""
from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])
    model_ready: bool
    classes: list[str] = []
    feature_count: int | None = None
    sequence_steps: int | None = None
    pose_model: str | None = None
    error: str | None = None


class WindowPrediction(BaseModel):
    start_sec: float
    end_sec: float
    label: str
    probabilities: dict[str, float]


class PersonPrediction(BaseModel):
    track_id: int = Field(description="한 영상 안의 추적 번호. 영구적인 사람 ID가 아님")
    action_label: str = Field(description="6개 동작 중 하나, 또는 UNCERTAIN / INSUFFICIENT_INPUT")
    raw_label: str | None = Field(description="기준 적용 전 1등 동작")
    confidence: float = Field(ge=0, le=1)
    margin: float = Field(description="1등과 2등 확률 차이")
    probabilities: dict[str, float]
    window_count: int
    window_agreement: float = Field(description="Window별 1등이 최종 결과와 같은 비율")
    valid_frames: int
    detected_frames: int
    interpolated_joints: int
    input_quality: str = Field(examples=["good", "fair", "poor"])
    mean_keypoint_conf: float = Field(0.0, description="사람 관절 17개의 평균 인식 Confidence")
    whole_probabilities: dict[str, float] = Field(default_factory=dict, description="학습과 같은 전체 구간 30 Step 예측")
    window_mean_probabilities: dict[str, float] = Field(default_factory=dict, description="2초 Window 예측 평균")
    timeline: list[WindowPrediction] = Field(default_factory=list, description="Window별 시간 구간과 확률")
    start_sec: float | None = None
    end_sec: float | None = None
    message: str | None = None


class VideoInfo(BaseModel):
    filename: str | None
    fps: float
    frame_count: int
    duration_sec: float
    width: int
    height: int


class PredictionResponse(BaseModel):
    status: str = Field(description="ok: 사람별 결과 있음, no_person: 영상은 정상이나 사람이 없음")
    message: str | None = None
    video: VideoInfo
    predictions: list[PersonPrediction]
    processing_ms: int
    settings: dict


class ErrorResponse(BaseModel):
    detail: str
