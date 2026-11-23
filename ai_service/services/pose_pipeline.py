"""영상 → YOLO Pose·ByteTrack → 사람(Track ID)별 38-D Frame Feature 시퀀스.

6~8일차와 같은 조건을 유지합니다.
- Pose 모델·image_size·person_confidence: project.json
- Tracker: bytetrack.yaml (day08_multi_person.json)
- Frame Feature: src.multi_person_utils.feature_from_keypoints (정규화 좌표 34 + 관절각 4)

추가한 점 (재학습 없음, 입력 품질 개선)
- 낮은 Confidence 관절은 같은 사람의 앞뒤 Frame 값으로 선형 보간합니다.
  관절이 순간적으로 튀는 값을 줄이기 위한 것으로 Puchała 외(2023)의 결측 관절 보정 아이디어입니다.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from src.multi_person_utils import feature_from_keypoints


class VideoReadError(ValueError):
    """영상 파일을 열 수 없거나 Frame이 없을 때."""


@dataclass
class TrackSequence:
    track_id: int
    frame_ids: list[int] = field(default_factory=list)
    keypoints: list[np.ndarray] = field(default_factory=list)  # (17, 2) 픽셀 좌표
    keypoint_conf: list[np.ndarray] = field(default_factory=list)  # (17,)
    box_conf: list[float] = field(default_factory=list)


@dataclass
class PersonFeatures:
    track_id: int
    features: np.ndarray  # (T, 38)
    frame_ids: np.ndarray  # (T,)
    detected_frames: int
    interpolated_joints: int
    mean_keypoint_conf: float
    mean_box_conf: float = 0.0


@dataclass
class VideoPoseResult:
    fps: float
    frame_count: int
    width: int
    height: int
    people: list[PersonFeatures]
    pose_seconds: float

    @property
    def duration_seconds(self) -> float:
        return self.frame_count / self.fps if self.fps > 0 else 0.0


def _to_numpy(value) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        return value.numpy()
    return np.asarray(value)


def interpolate_low_confidence(
    keypoints: np.ndarray,
    keypoint_conf: np.ndarray,
    frame_ids: np.ndarray,
    min_confidence: float,
) -> tuple[np.ndarray, int]:
    """(T, 17, 2) 관절 좌표에서 Confidence가 낮은 값을 같은 관절의 앞뒤 Frame으로 보간합니다.

    같은 관절이 영상 전체에서 믿을 만한 값이 2개 미만이면 원래 값을 그대로 둡니다.
    반환: (보간된 좌표, 보간한 관절 값 개수)
    """
    output = keypoints.astype(np.float32).copy()
    replaced = 0
    for joint in range(output.shape[1]):
        good = keypoint_conf[:, joint] >= min_confidence
        bad = ~good
        if not bad.any() or good.sum() < 2:
            continue
        for axis in range(2):
            output[bad, joint, axis] = np.interp(
                frame_ids[bad], frame_ids[good], output[good, joint, axis]
            )
        replaced += int(bad.sum())
    return output, replaced


class PosePipeline:
    def __init__(
        self,
        weights_path: Path,
        image_size: int,
        person_confidence: float,
        tracker: str,
        device: str | int = "cpu",
    ):
        self.weights_path = str(weights_path)
        self.image_size = int(image_size)
        self.person_confidence = float(person_confidence)
        self.tracker = tracker
        self.device = device
        # 서버 시작 시 한 번 불러와 가중치 파일이 정상인지 확인합니다.
        YOLO(self.weights_path)

    def _new_model(self) -> YOLO:
        # Tracker 상태(Track ID)는 모델 객체에 남으므로 요청마다 새 객체를 씁니다.
        # yolo11n-pose는 6MB라 불러오는 시간은 짧습니다.
        return YOLO(self.weights_path)

    def track_video(self, video_path: Path) -> tuple[dict[int, TrackSequence], float, int, int, int]:
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            raise VideoReadError("영상을 열 수 없습니다. MP4 파일인지 확인해 주세요.")

        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)

        model = self._new_model()
        tracks: dict[int, TrackSequence] = {}
        frame_index = 0
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                result = model.track(
                    frame,
                    persist=True,
                    tracker=self.tracker,
                    imgsz=self.image_size,
                    conf=self.person_confidence,
                    device=self.device,
                    verbose=False,
                )[0]
                self._collect(result, frame_index, tracks)
                frame_index += 1
        finally:
            capture.release()

        if frame_index == 0:
            raise VideoReadError("영상에서 Frame을 읽지 못했습니다. 손상된 파일일 수 있습니다.")
        if fps <= 0:
            fps = 30.0
        return tracks, fps, frame_index, width, height

    @staticmethod
    def _collect(result, frame_index: int, tracks: dict[int, TrackSequence]) -> None:
        boxes = result.boxes
        keypoints = result.keypoints
        if boxes is None or keypoints is None or keypoints.xy is None or len(boxes) == 0:
            return

        xy = _to_numpy(keypoints.xy)
        conf = _to_numpy(keypoints.conf) if keypoints.conf is not None else np.ones(xy.shape[:2], dtype=np.float32)
        box_conf = _to_numpy(boxes.conf)
        if boxes.id is not None:
            ids = _to_numpy(boxes.id).astype(int)
        elif len(xy) == 1:
            # Tracker가 첫 Frame에 ID를 아직 붙이지 않은 경우: 한 사람이면 1번으로 둡니다.
            ids = np.array([1])
        else:
            return

        for person, track_id in enumerate(ids[: len(xy)]):
            if xy[person].shape != (17, 2):
                continue
            track = tracks.setdefault(int(track_id), TrackSequence(track_id=int(track_id)))
            track.frame_ids.append(frame_index)
            track.keypoints.append(xy[person].astype(np.float32))
            track.keypoint_conf.append(conf[person].astype(np.float32))
            track.box_conf.append(float(box_conf[person]))

    def extract(
        self,
        video_path: Path,
        interpolate: bool,
        keypoint_min_confidence: float,
    ) -> VideoPoseResult:
        started = time.perf_counter()
        tracks, fps, frame_count, width, height = self.track_video(video_path)

        people = []
        for track in tracks.values():
            frame_ids = np.asarray(track.frame_ids, dtype=np.int32)
            keypoints = np.stack(track.keypoints)
            keypoint_conf = np.stack(track.keypoint_conf)
            replaced = 0
            if interpolate:
                keypoints, replaced = interpolate_low_confidence(
                    keypoints, keypoint_conf, frame_ids.astype(np.float32), keypoint_min_confidence
                )

            features, valid_ids = [], []
            for frame_id, points in zip(frame_ids, keypoints):
                feature = feature_from_keypoints(points)
                if feature is not None:
                    features.append(feature)
                    valid_ids.append(int(frame_id))

            people.append(
                PersonFeatures(
                    track_id=track.track_id,
                    features=np.stack(features) if features else np.empty((0, 38), dtype=np.float32),
                    frame_ids=np.asarray(valid_ids, dtype=np.int32),
                    detected_frames=len(frame_ids),
                    interpolated_joints=replaced,
                    mean_keypoint_conf=float(keypoint_conf.mean()),
                    mean_box_conf=float(np.mean(track.box_conf)),
                )
            )

        people.sort(key=lambda p: p.track_id)
        return VideoPoseResult(
            fps=fps,
            frame_count=frame_count,
            width=width,
            height=height,
            people=people,
            pose_seconds=time.perf_counter() - started,
        )
