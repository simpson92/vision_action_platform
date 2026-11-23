"""FastAPI AI 서버 호출. 영상 파일을 multipart로 보내고 응답·타임아웃·오류를 구분합니다."""
from pathlib import Path

import requests
from django.conf import settings


class AIServiceError(Exception):
    """재시도해도 소용없는 오류 (잘못된 영상 등)."""


class AIServiceUnavailable(Exception):
    """잠깐 뒤 다시 시도할 만한 오류 (서버 미기동, 타임아웃)."""


def predict_video(video_path: Path) -> dict:
    url = settings.FASTAPI_URL.rstrip("/") + "/predict/video"
    try:
        with open(video_path, "rb") as file:
            response = requests.post(
                url,
                files={"file": (Path(video_path).name, file, "video/mp4")},
                timeout=(5, settings.FASTAPI_TIMEOUT_SECONDS),
            )
    except requests.Timeout as exc:
        raise AIServiceUnavailable(f"AI 서버 응답 시간 초과({settings.FASTAPI_TIMEOUT_SECONDS:.0f}초)") from exc
    except requests.ConnectionError as exc:
        raise AIServiceUnavailable("AI 서버에 연결할 수 없습니다") from exc

    if response.status_code in (502, 503, 504):
        raise AIServiceUnavailable(_detail(response))
    if response.status_code >= 400:
        raise AIServiceError(_detail(response))
    return response.json()


def _detail(response) -> str:
    try:
        return str(response.json().get("detail", response.text))
    except ValueError:
        return f"AI 서버 오류 HTTP {response.status_code}"
