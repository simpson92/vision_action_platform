"""POST /predict/video: Celery Worker가 보낸 영상 한 건을 분석해 사람별 결과를 반환합니다.

FastAPI는 DB에 저장하지 않습니다. 저장은 Celery Worker가 Django ORM으로 합니다.
"""
from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from schemas import ErrorResponse, PredictionResponse
from services.action_inference import InferenceOptions, predict_video
from services.pose_pipeline import VideoReadError

router = APIRouter(tags=["predictions"])

ALLOWED_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv", ".webm"}


@router.post(
    "/predict/video",
    response_model=PredictionResponse,
    responses={400: {"model": ErrorResponse}, 413: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
async def predict_video_endpoint(request: Request, file: UploadFile = File(..., description="분석할 영상 (MP4 권장)")):
    state = request.app.state
    if getattr(state, "bundle", None) is None:
        raise HTTPException(status_code=503, detail=f"모델이 준비되지 않았습니다: {state.load_error}")

    settings = state.settings
    suffix = Path(file.filename or "video.mp4").suffix.lower() or ".mp4"
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 형식입니다: {suffix}. MP4로 올려 주세요.")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"파일이 {settings.max_upload_mb}MB를 넘습니다.")

    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"input{suffix}"
        path.write_bytes(data)
        try:
            # 추론은 CPU를 오래 쓰므로 이벤트 루프를 막지 않게 별도 스레드에서 실행합니다.
            async with state.inference_lock:
                pose = await asyncio.to_thread(
                    state.pose.extract, path, settings.keypoint_interpolation, settings.keypoint_min_confidence
                )
                options = InferenceOptions(
                    min_valid_frames=settings.min_valid_frames,
                    confidence_threshold=settings.confidence_threshold,
                    margin_threshold=settings.margin_threshold,
                    window_seconds=settings.window_seconds,
                    window_stride_seconds=settings.window_stride_seconds,
                )
                predictions = predict_video(state.bundle, pose, options)
        except VideoReadError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    usable = [p for p in predictions if p["action_label"] != "INSUFFICIENT_INPUT"]
    if not predictions:
        status, message = "no_person", "영상에서 사람을 찾지 못했습니다."
    elif not usable:
        status, message = "no_person", "사람이 잠깐만 보여 동작을 판단할 Frame이 부족합니다."
    else:
        status, message = "ok", None

    return PredictionResponse(
        status=status,
        message=message,
        video={
            "filename": file.filename,
            "fps": round(pose.fps, 2),
            "frame_count": pose.frame_count,
            "duration_sec": round(pose.duration_seconds, 2),
            "width": pose.width,
            "height": pose.height,
        },
        predictions=predictions,
        processing_ms=int((time.perf_counter() - started) * 1000),
        settings={
            "confidence_threshold": settings.confidence_threshold,
            "margin_threshold": settings.margin_threshold,
            "window_seconds": settings.window_seconds,
            "keypoint_interpolation": settings.keypoint_interpolation,
        },
    )
