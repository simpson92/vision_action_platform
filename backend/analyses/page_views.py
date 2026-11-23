"""HTML 화면: 분석 화면(로그인), 상세, 관리자 전용 대시보드(ORM 집계 → Chart.js)."""
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache

import requests

from .models import ACTION_CHOICES, AnalysisJob, PersonPrediction


@login_required
def index(request):
    cameras = [{"index": i, "name": f"카메라 {i + 1}"} for i in range(len(settings.IP_WEBCAM_ALLOWED_URLS))]
    recent = AnalysisJob.objects.filter(user=request.user).prefetch_related("predictions")[:10]
    return render(request, "analyses/index.html", {
        "cameras": cameras,
        "capture_seconds": settings.IP_WEBCAM_CAPTURE_SECONDS,
        "actions": ACTION_CHOICES,
        "recent": recent,
        "max_upload_mb": settings.MAX_UPLOAD_MB,
        "rules": {
            "confidence": settings.CONFIDENCE_THRESHOLD,
            "margin": settings.MARGIN_THRESHOLD,
            "chance": round(1 / settings.ACTION_CLASS_COUNT, 4),
            "confidence_pct": round(settings.CONFIDENCE_THRESHOLD * 100, 1),
            "margin_pct": round(settings.MARGIN_THRESHOLD * 100, 1),
            "chance_pct": round(100 / settings.ACTION_CLASS_COUNT, 1),
        },
    })


@login_required
def detail(request, pk):
    qs = AnalysisJob.objects.prefetch_related("predictions")
    if not request.user.is_staff:
        qs = qs.filter(user=request.user)
    job = get_object_or_404(qs, pk=pk)
    return render(request, "analyses/detail.html", {"job": job})


@staff_member_required
def dashboard(request):
    # 차트 1: 6개 Action별 예측 건수 (판단 보류·입력 부족은 따로)
    counts = dict(PersonPrediction.objects.values_list("action_label").annotate(n=Count("id")))
    action_chart = {
        "labels": [label for _, label in ACTION_CHOICES] + ["판단 보류"],
        "values": [counts.get(key, 0) for key, _ in ACTION_CHOICES] + [counts.get("UNCERTAIN", 0)],
    }
    # 차트 2: 작업 상태별 건수
    status_counts = dict(AnalysisJob.objects.values_list("status").annotate(n=Count("id")))
    status_chart = {
        "labels": [label for _, label in AnalysisJob.Status.choices],
        "keys": [key for key, _ in AnalysisJob.Status.choices],
        "values": [status_counts.get(key, 0) for key, _ in AnalysisJob.Status.choices],
    }
    # 선택 차트: 입력 방식별 건수와 평균 처리 시간
    by_input = AnalysisJob.objects.values("input_type").annotate(
        n=Count("id"),
        avg_ms=Avg("processing_ms", filter=Q(status=AnalysisJob.Status.SUCCESS)),
    )
    input_names = dict(AnalysisJob.InputType.choices)
    input_chart = {
        "labels": [input_names.get(r["input_type"], r["input_type"]) for r in by_input],
        "values": [r["n"] for r in by_input],
        "avg_seconds": [round((r["avg_ms"] or 0) / 1000, 2) for r in by_input],
    }
    summary = {
        "jobs": AnalysisJob.objects.count(),
        "users": AnalysisJob.objects.values("user").distinct().count(),
        "predictions": PersonPrediction.objects.count(),
        "failures": status_counts.get(AnalysisJob.Status.FAILURE, 0),
    }
    recent = AnalysisJob.objects.select_related("user").prefetch_related("predictions")[:15]
    return render(request, "analyses/dashboard.html", {
        "action_chart": action_chart,
        "status_chart": status_chart,
        "input_chart": input_chart,
        "summary": summary,
        "recent": recent,
    })


def snapshot_url(camera_url: str) -> str | None:
    """IP Webcam 앱의 영상 주소(.../video)에서 사진 한 장 주소(.../shot.jpg)를 만듭니다."""
    base = camera_url.rstrip("/")
    if base.endswith("/video"):
        return base[: -len("/video")] + "/shot.jpg"
    return None


@login_required
@never_cache
def camera_snapshot(request, index):
    """IP Webcam 미리보기: 허용 목록의 카메라에서 현재 사진 한 장을 받아 그대로 전달합니다.

    브라우저가 카메라 주소를 직접 알 필요가 없도록 서버가 대신 가져옵니다(주소 비노출).
    영상 스트림을 계속 붙잡지 않고 사진을 짧게 여러 번 요청하는 방식이라 웹 서버 작업자를 오래 막지 않습니다.
    """
    cameras = settings.IP_WEBCAM_ALLOWED_URLS
    if not 0 <= index < len(cameras):
        raise Http404("허용 목록에 없는 카메라입니다.")
    url = snapshot_url(cameras[index])
    if url is None:
        return HttpResponse("이 카메라 주소는 미리보기를 지원하지 않습니다.", status=404, content_type="text/plain; charset=utf-8")
    try:
        response = requests.get(url, timeout=settings.IP_WEBCAM_CONNECT_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException:
        return HttpResponse("카메라에 연결하지 못했습니다.", status=502, content_type="text/plain; charset=utf-8")
    return HttpResponse(response.content, content_type=response.headers.get("Content-Type", "image/jpeg"))
