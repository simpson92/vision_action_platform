"""Celery 작업: 영상 확보(업로드 파일 또는 IP Webcam 수집) → FastAPI 추론 → Django ORM 저장."""
import logging
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .camera_capture import CameraError, capture_clip
from .models import AnalysisJob, PersonPrediction
from .services import AIServiceError, AIServiceUnavailable, predict_video

logger = logging.getLogger(__name__)

DETAIL_KEYS = ("timeline", "whole_probabilities", "window_mean_probabilities", "window_agreement",
               "detected_frames", "interpolated_joints", "mean_keypoint_conf")


def _fail(job_id: int, message: str) -> None:
    AnalysisJob.objects.filter(pk=job_id).update(
        status=AnalysisJob.Status.FAILURE, error_message=message[:2000], completed_at=timezone.now()
    )


@shared_task(bind=True, max_retries=2, default_retry_delay=5)
def run_analysis(self, job_id: int) -> dict:
    job = AnalysisJob.objects.filter(pk=job_id).first()
    if job is None:  # 처리 전에 삭제된 작업
        return {"job_id": job_id, "status": "deleted"}

    AnalysisJob.objects.filter(pk=job_id).update(
        status=AnalysisJob.Status.STARTED, started_at=job.started_at or timezone.now(),
        celery_task_id=self.request.id or job.celery_task_id,
    )

    try:
        # 1) 분석할 영상 확보
        if job.input_type == AnalysisJob.InputType.IP_WEBCAM and not job.video:
            cameras = settings.IP_WEBCAM_ALLOWED_URLS
            if job.camera_index is None or job.camera_index >= len(cameras):
                raise CameraError("허용 목록에 없는 카메라입니다.")
            relative = Path("analyses") / "ip_webcam" / f"job_{job.pk}.webm"
            capture_clip(cameras[job.camera_index], job.capture_seconds or settings.IP_WEBCAM_CAPTURE_SECONDS,
                         Path(settings.MEDIA_ROOT) / relative, settings.IP_WEBCAM_CONNECT_TIMEOUT)
            job.video.name = str(relative)
            AnalysisJob.objects.filter(pk=job_id).update(video=job.video.name)
        if not job.video:
            raise AIServiceError("분석할 영상이 없습니다.")

        # 2) FastAPI 추론 (FastAPI는 DB를 모름)
        result = predict_video(Path(job.video.path))
    except AIServiceUnavailable as exc:
        if self.request.retries < self.max_retries:
            logger.warning("job %s: AI 서버 재시도 (%s)", job_id, exc)
            raise self.retry(exc=exc)
        _fail(job_id, f"AI 서버 오류: {exc}")
        return {"job_id": job_id, "status": "FAILURE"}
    except (AIServiceError, CameraError) as exc:
        _fail(job_id, str(exc))
        return {"job_id": job_id, "status": "FAILURE"}
    except Exception as exc:  # 예상 못 한 오류도 실패 상태로 남김
        logger.exception("job %s 실패", job_id)
        _fail(job_id, f"알 수 없는 오류: {exc}")
        return {"job_id": job_id, "status": "FAILURE"}

    # 3) 결과 저장: 작업 상태와 사람별 예측을 한 트랜잭션으로
    with transaction.atomic():
        job = AnalysisJob.objects.select_for_update().filter(pk=job_id).first()
        if job is None:
            return {"job_id": job_id, "status": "deleted"}
        job.predictions.all().delete()
        PersonPrediction.objects.bulk_create([
            PersonPrediction(
                job=job,
                track_id=p["track_id"],
                action_label=p["action_label"],
                raw_label=p.get("raw_label") or "",
                confidence=p.get("confidence", 0.0),
                margin=p.get("margin", 0.0),
                probabilities=p.get("probabilities", {}),
                details={key: p[key] for key in DETAIL_KEYS if key in p},
                window_count=p.get("window_count", 0),
                valid_frames=p.get("valid_frames", 0),
                input_quality=p.get("input_quality", ""),
                start_sec=p.get("start_sec"),
                end_sec=p.get("end_sec"),
            )
            for p in result.get("predictions", [])
        ])
        job.status = AnalysisJob.Status.SUCCESS
        job.result_message = (result.get("message") or "")[:255]
        job.error_message = ""
        job.processing_ms = result.get("processing_ms")
        video = result.get("video") or {}
        job.video_duration_sec = video.get("duration_sec")
        job.video_meta = {key: video[key] for key in ("fps", "frame_count", "width", "height") if key in video}
        job.completed_at = timezone.now()
        job.save()
    return {"job_id": job_id, "status": "SUCCESS", "people": len(result.get("predictions", []))}
