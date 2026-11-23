"""분석 화면 상단 지표·그래프용 집계 (본인 작업만, Django ORM).

index 화면 첫 표시와 GET /api/analyses/stats/ 가 같은 함수를 씁니다.
"""
from django.db.models import Avg, Count, Q
from django.utils import timezone

from .models import ACTION_CHOICES, AnalysisJob, PersonPrediction

UNDECIDED = ("UNCERTAIN", "INSUFFICIENT_INPUT")


def _rate(part, whole):
    return round(part * 100 / whole) if whole else None


def user_stats(user, recent_n=10):
    jobs = AnalysisJob.objects.filter(user=user)
    today = timezone.localdate()
    agg = jobs.aggregate(
        total=Count("id"),
        success=Count("id", filter=Q(status=AnalysisJob.Status.SUCCESS)),
        failure=Count("id", filter=Q(status=AnalysisJob.Status.FAILURE)),
        today=Count("id", filter=Q(created_at__date=today)),
        avg_ms=Avg("processing_ms", filter=Q(status=AnalysisJob.Status.SUCCESS)),
    )
    finished = agg["success"] + agg["failure"]

    preds = PersonPrediction.objects.filter(job__user=user)
    pred_total = preds.count()
    undecided = preds.filter(action_label__in=UNDECIDED).count()

    # 실제 동작을 고른 작업 중 AI가 맞힌 비율
    labelled = jobs.filter(status=AnalysisJob.Status.SUCCESS).exclude(expected_action="").prefetch_related("predictions")
    states = [job.match_state for job in labelled]
    compared = [s for s in states if s in ("match", "mismatch")]

    # 최근 작업(오래된 것 → 최신) 기준 작은 추이 그래프
    recent = list(jobs.prefetch_related("predictions")[:recent_n])[::-1]
    spark_count, spark_success, spark_decided, spark_ms = [], [], [], []
    done = ok = decided = people = 0
    base = agg["total"] - len(recent)
    for i, job in enumerate(recent, start=1):
        spark_count.append(base + i)
        if job.is_finished:
            done += 1
            ok += job.status == AnalysisJob.Status.SUCCESS
        spark_success.append(_rate(ok, done) or 0)
        job_preds = list(job.predictions.all())
        people += len(job_preds)
        decided += sum(p.is_decided for p in job_preds)
        spark_decided.append(_rate(decided, people) or 0)
        if job.processing_ms:
            spark_ms.append(round(job.processing_ms / 1000, 2))

    trend = [
        {"label": f"#{job.pk}", "confidence": round(job.top_prediction.confidence, 3),
         "decided": job.top_prediction.is_decided}
        for job in recent if job.status == AnalysisJob.Status.SUCCESS and job.top_prediction
    ]

    counts = dict(preds.values_list("action_label").annotate(n=Count("id")))
    distribution = {
        "labels": [label for _, label in ACTION_CHOICES] + ["판단 보류"],
        "values": [counts.get(key, 0) for key, _ in ACTION_CHOICES] + [sum(counts.get(k, 0) for k in UNDECIDED)],
    }

    last = jobs.filter(status=AnalysisJob.Status.SUCCESS, processing_ms__isnull=False).first()
    return {
        "total": agg["total"],
        "today": agg["today"],
        "success": agg["success"],
        "finished": finished,
        "success_rate": _rate(agg["success"], finished),
        "predictions": pred_total,
        "undecided": undecided,
        "decided_rate": _rate(pred_total - undecided, pred_total),
        "avg_seconds": round(agg["avg_ms"] / 1000, 1) if agg["avg_ms"] else None,
        "last_seconds": round(last.processing_ms / 1000, 1) if last else None,
        "labelled": len(compared),
        "matched": compared.count("match"),
        "accuracy": _rate(compared.count("match"), len(compared)),
        "spark": {"count": spark_count, "success": spark_success, "decided": spark_decided, "seconds": spark_ms},
        "trend": trend,
        "distribution": distribution,
    }
