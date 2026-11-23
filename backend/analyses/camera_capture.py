"""허용된 IP Webcam에서 정해진 시간(기본 8초)만 Frame을 읽어 WebM 영상으로 저장합니다.

- 주소는 사용자 입력이 아니라 .env의 IP_WEBCAM_ALLOWED_URLS 목록에서 번호로 고릅니다.
- 수집 시간은 "입력 영상의 길이"이고, 연결·추론 시간은 별도입니다.
- 실제 FPS로 저장해 영상 길이가 실제 시간과 맞게 합니다.
"""
import time
from pathlib import Path

import cv2


class CameraError(Exception):
    pass


def capture_clip(url: str, seconds: float, output_path: Path, connect_timeout: float = 5.0) -> dict:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(url)
    capture.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, connect_timeout * 1000)
    capture.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, connect_timeout * 1000)
    if not capture.isOpened():
        raise CameraError("카메라에 연결하지 못했습니다. 휴대폰 IP Webcam 앱이 켜져 있고 같은 Wi-Fi인지 확인해 주세요.")

    frames = []
    started = time.monotonic()
    last_frame_at = started
    try:
        while time.monotonic() - started < seconds:
            ok, frame = capture.read()
            now = time.monotonic()
            if not ok:
                if now - last_frame_at > connect_timeout:
                    raise CameraError("카메라 연결이 끊겼습니다.")
                continue
            frames.append(frame)
            last_frame_at = now
    finally:
        capture.release()

    elapsed = time.monotonic() - started
    if len(frames) < 10:
        raise CameraError(f"{seconds:.0f}초 동안 Frame을 {len(frames)}개만 받았습니다. 네트워크를 확인해 주세요.")

    fps = max(len(frames) / elapsed, 1.0)
    height, width = frames[0].shape[:2]
    # 브라우저에서 바로 재생되도록 WebM(VP8)으로 저장. (pip판 OpenCV는 H.264 인코더가 없고,
    # mp4v(MPEG-4 Part 2)는 Chrome 등이 재생하지 못해 검은 화면이 됨)
    writer = cv2.VideoWriter(str(output_path), cv2.VideoWriter_fourcc(*"VP80"), fps, (width, height))
    if not writer.isOpened():
        raise CameraError("수집한 영상을 저장하지 못했습니다.")
    for frame in frames:
        writer.write(frame)
    writer.release()
    return {"frames": len(frames), "fps": round(fps, 2), "seconds": round(elapsed, 2)}
