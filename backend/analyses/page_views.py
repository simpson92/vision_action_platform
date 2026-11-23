"""HTML 화면: 분석 화면(로그인), 상세, 관리자 전용 대시보드(ORM 집계 → Chart.js)."""
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, render

from .models import ACTION_CHOICES, AnalysisJob, PersonPrediction
from .stats import user_stats


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
        "stats": user_stats(request.user),
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
