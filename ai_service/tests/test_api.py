"""AI 서버 테스트 (T01 모델 불러오기, 오류 처리, 사람 없는 영상).

실행: ai_service 폴더에서 `python -m pytest -q`
테스트 영상이 있으면(TEST_VIDEO_DIR, 기본 ../test_videos) 실제 추론까지 확인합니다.
"""
from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from main import app

VIDEO_DIR = Path(os.getenv("TEST_VIDEO_DIR", Path(__file__).resolve().parents[2] / "test_videos"))


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health_model_ready(client):
    body = client.get("/health").json()
    assert body["model_ready"] is True
    assert body["feature_count"] == 1140
    assert body["sequence_steps"] == 30
    assert len(body["classes"]) == 6


def test_rejects_wrong_extension(client):
    r = client.post("/predict/video", files={"file": ("note.txt", b"hello", "text/plain")})
    assert r.status_code == 400


def test_rejects_broken_video(client):
    r = client.post("/predict/video", files={"file": ("broken.mp4", b"not a video", "video/mp4")})
    assert r.status_code == 422


def test_empty_scene_returns_no_person(client, tmp_path):
    path = tmp_path / "empty.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (320, 240))
    for _ in range(20):
        writer.write(np.full((240, 320, 3), 200, dtype=np.uint8))
    writer.release()
    r = client.post("/predict/video", files={"file": ("empty.mp4", path.read_bytes(), "video/mp4")})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "no_person"
    assert body["predictions"] == []


# 판단을 확정(UNCERTAIN 아님)하는 S03 영상 3개: 확정한 결과는 정답이어야 함
@pytest.mark.parametrize("name,expected", [
    ("S03_A001_T01.mp4", "bend_return"),
    ("S03_A002_T01.mp4", "leg_raise_lower"),
    ("S03_A006_T01.mp4", "wave"),
])
def test_real_video_top1(client, name, expected):
    path = VIDEO_DIR / name
    if not path.exists():
        pytest.skip(f"테스트 영상 없음: {path}")
    r = client.post("/predict/video", files={"file": (name, path.read_bytes(), "video/mp4")})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    main = max(body["predictions"], key=lambda p: p["valid_frames"])
    assert main["action_label"] == expected
    # 화면 그래프용 구간별 확률: Window 수와 같고 시간 순서
    assert len(main["timeline"]) == main["window_count"]
    starts = [w["start_sec"] for w in main["timeline"]]
    assert starts == sorted(starts)
    assert set(main["whole_probabilities"]) == set(main["probabilities"])
