"""사람별 Frame Feature → 30 Step Sequence → Random Forest 예측.

학습 때(34·35번 스크립트)처럼 동작 구간 전체를 30 Step으로 리샘플링해 1,140개 Feature를 만듭니다.

추가한 점 (재학습 없음)
1. 전체 구간 + 여러 Window 확률 평균: 학습과 같은 "전체 구간 30 Step" 예측에, 2초 Window(0.5초 간격)
   예측들의 평균을 반씩 섞습니다. 7일차 PredictionStabilizer(다수결)를 확률 평균으로 바꾼 것으로,
   한 번의 예측이 우연히 틀리는 것을 줄입니다. S02(검증용 사람) 영상에서 Top-1이 2/6 → 4/6으로 올라
   이 방식을 골랐고, S03(테스트)은 선택에 쓰지 않았습니다 (결과는 README 참고).
2. 판단 불확실: 1등 확률이 CONFIDENCE_THRESHOLD 미만이거나 1등과 2등의 차이가 MARGIN_THRESHOLD 미만이면
   UNCERTAIN으로 표시합니다. 학습하지 않은 동작도 6개 중 하나로 나오는 문제에 대한 대응입니다.
   7일차의 0.55 기준은 이 모델(S01 6 clip 학습, 확률이 0.2~0.3대)에서는 모든 결과를 UNKNOWN으로 만들었기 때문에
   기준을 S02(검증용 사람) 영상으로 다시 맞췄습니다. S03(테스트)은 기준을 정하는 데 쓰지 않습니다.
3. 입력 품질: 사람이 검출된 Frame 비율과 평균 관절 Confidence로 good/fair/poor를 함께 반환합니다.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from services.model_loader import ActionModelBundle
from services.pose_pipeline import PersonFeatures, VideoPoseResult
from src.sequence_utils import flatten_sequence, resample_sequence

UNCERTAIN = "UNCERTAIN"
INSUFFICIENT = "INSUFFICIENT_INPUT"


@dataclass
class InferenceOptions:
    min_valid_frames: int
    confidence_threshold: float
    margin_threshold: float
    window_seconds: float
    window_stride_seconds: float


def _windows(frame_ids: np.ndarray, fps: float, options: InferenceOptions) -> list[tuple[int, int]]:
    """(시작 index, 끝 index) 목록. 짧은 영상은 전체 1개, 긴 영상은 겹치는 Window 여러 개."""
    span_seconds = (frame_ids[-1] - frame_ids[0]) / fps
    if span_seconds <= options.window_seconds * 1.25:
        return [(0, len(frame_ids))]

    window_frames = options.window_seconds * fps
    stride_frames = max(options.window_stride_seconds * fps, 1.0)
    windows = []
    start_frame = float(frame_ids[0])
    while start_frame + window_frames <= frame_ids[-1] + stride_frames:
        end_frame = start_frame + window_frames
        idx = np.where((frame_ids >= start_frame) & (frame_ids < end_frame))[0]
        if len(idx) >= options.min_valid_frames:
            windows.append((int(idx[0]), int(idx[-1]) + 1))
        start_frame += stride_frames
    return windows or [(0, len(frame_ids))]


def _input_quality(person: PersonFeatures, frame_count: int) -> str:
    detected_ratio = person.detected_frames / max(frame_count, 1)
    if detected_ratio >= 0.8 and person.mean_keypoint_conf >= 0.6:
        return "good"
    if detected_ratio >= 0.5 and person.mean_keypoint_conf >= 0.4:
        return "fair"
    return "poor"


def predict_person(
    bundle: ActionModelBundle,
    person: PersonFeatures,
    fps: float,
    frame_count: int,
    options: InferenceOptions,
) -> dict:
    base = {
        "track_id": person.track_id,
        "valid_frames": int(len(person.frame_ids)),
        "detected_frames": int(person.detected_frames),
        "interpolated_joints": int(person.interpolated_joints),
        "input_quality": _input_quality(person, frame_count),
        "mean_keypoint_conf": round(float(person.mean_keypoint_conf), 3),
    }
    if len(person.frame_ids) < options.min_valid_frames:
        return {
            **base,
            "action_label": INSUFFICIENT,
            "raw_label": None,
            "confidence": 0.0,
            "margin": 0.0,
            "probabilities": {},
            "window_count": 0,
            "window_agreement": 0.0,
            "start_sec": round(float(person.frame_ids[0]) / fps, 2) if len(person.frame_ids) else None,
            "end_sec": round(float(person.frame_ids[-1]) / fps, 2) if len(person.frame_ids) else None,
            "message": f"유효 Frame이 {len(person.frame_ids)}개라 {options.min_valid_frames}개 미만입니다.",
        }

    def flat(start: int, end: int) -> np.ndarray:
        sequence = resample_sequence(
            person.features[start:end],
            person.frame_ids[start:end],
            target_steps=bundle.sequence_steps,
        )
        return flatten_sequence(sequence)

    # ① 학습과 같은 방식: 사람이 보인 구간 전체를 30 Step으로
    whole = flat(0, len(person.frame_ids))
    # ② 짧은 Window 여러 개 (구간이 짧으면 ①과 같은 1개)
    spans = _windows(person.frame_ids, fps, options)
    window_rows = [flat(a, b) for a, b in spans]
    matrix = np.stack([whole, *window_rows])
    if matrix.shape[1] != bundle.feature_count:
        raise RuntimeError(f"입력 Feature 수 {matrix.shape[1]} != 모델 {bundle.feature_count}")

    probs = bundle.model.predict_proba(matrix)
    window_probs = probs[1:]
    # 전체 구간 확률과 Window 평균 확률을 반씩 섞음 (S02 검증 영상 기준으로 고른 방식)
    mean_probs = 0.5 * probs[0] + 0.5 * window_probs.mean(axis=0)
    best = int(np.argmax(mean_probs))
    raw_label = bundle.classes[best]
    confidence = float(mean_probs[best])
    margin = float(confidence - np.sort(mean_probs)[-2])
    decided = confidence >= options.confidence_threshold and margin >= options.margin_threshold
    agreement = float((window_probs.argmax(axis=1) == best).mean())
    as_dict = lambda row: {c: round(float(p), 4) for c, p in zip(bundle.classes, row)}  # noqa: E731
    # 화면 그래프용: 영상 구간(Window)마다 확률이 어떻게 바뀌었는지
    timeline = [
        {
            "start_sec": round(float(person.frame_ids[a]) / fps, 2),
            "end_sec": round(float(person.frame_ids[b - 1]) / fps, 2),
            "label": bundle.classes[int(np.argmax(row))],
            "probabilities": as_dict(row),
        }
        for (a, b), row in zip(spans, window_probs)
    ]

    return {
        **base,
        "action_label": raw_label if decided else UNCERTAIN,
        "raw_label": raw_label,
        "confidence": round(confidence, 4),
        "margin": round(margin, 4),
        "probabilities": {c: round(float(p), 4) for c, p in zip(bundle.classes, mean_probs)},
        "window_count": int(len(window_rows)),
        "window_agreement": round(agreement, 3),
        "whole_probabilities": as_dict(probs[0]),
        "window_mean_probabilities": as_dict(window_probs.mean(axis=0)),
        "timeline": timeline,
        "start_sec": round(float(person.frame_ids[0]) / fps, 2),
        "end_sec": round(float(person.frame_ids[-1]) / fps, 2),
        "message": None if decided else "1등 동작의 확률이 낮거나 2등과 차이가 작아 판단을 보류합니다.",
    }


def predict_video(bundle: ActionModelBundle, pose: VideoPoseResult, options: InferenceOptions) -> list[dict]:
    return [predict_person(bundle, person, pose.fps, pose.frame_count, options) for person in pose.people]
