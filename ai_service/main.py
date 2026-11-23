"""FastAPI AI 추론 서버.

- 서버 시작 시 6일차 모델·JSON·YOLO Pose를 한 번 불러와 app.state에 보관하고 요청마다 재사용합니다.
- GET /health: 서버와 모델 준비 상태
- POST /predict/video: 영상 → 사람별 동작 예측 JSON
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from routers import predictions
from schemas import HealthResponse
from services.model_loader import load_action_model
from services.pose_pipeline import PosePipeline
from settings import load_settings
from src.common import resolve_device

logger = logging.getLogger("ai_service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    app.state.settings = settings
    app.state.bundle = None
    app.state.pose = None
    app.state.load_error = None
    # YOLO 추론은 한 번에 한 건씩 처리해 CPU·메모리 사용을 일정하게 유지합니다.
    app.state.inference_lock = asyncio.Lock()
    try:
        app.state.bundle = load_action_model(settings.model_dir)
        app.state.pose = PosePipeline(
            weights_path=settings.model_dir / settings.pose_model,
            image_size=settings.image_size,
            person_confidence=settings.person_confidence,
            tracker=settings.tracker,
            device=resolve_device("auto"),
        )
        logger.info("모델 준비 완료: %s", app.state.bundle.classes)
    except Exception as exc:  # 모델이 없어도 /health로 원인을 확인할 수 있게 서버는 띄웁니다.
        app.state.load_error = str(exc)
        logger.exception("모델 준비 실패")
    yield


app = FastAPI(
    title="Vision Action AI Service",
    description="YOLO Pose + 6일차 Random Forest로 영상 속 사람별 동작을 예측합니다.",
    version="1.0.0",
    lifespan=lifespan,
)
app.include_router(predictions.router)


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health():
    bundle = app.state.bundle
    if bundle is None:
        return HealthResponse(status="error", model_ready=False, error=app.state.load_error)
    return HealthResponse(
        status="ok",
        model_ready=True,
        classes=bundle.classes,
        feature_count=bundle.feature_count,
        sequence_steps=bundle.sequence_steps,
        pose_model=app.state.settings.pose_model,
    )
