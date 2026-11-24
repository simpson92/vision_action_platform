"""분석 이력 검색·필터 (화면과 API가 같이 씀): 제목/파일 이름, 예측 동작, 상태, 날짜."""
from django.db.models import Q
from django.utils.dateparse import parse_date

from .models import ACTION_LABELS, AnalysisJob

FILTER_KEYS = ("q", "action", "status", "date_from", "date_to")
HOLD_LABELS = ("UNCERTAIN", "INSUFFICIENT_INPUT")


def read_filters(params) -> dict:
    """GET 값 중 쓸 수 있는 것만 남깁니다. 잘못된 값은 조용히 무시합니다."""
    values = {key: (params.get(key) or "").strip() for key in FILTER_KEYS}
    values["q"] = values["q"][:100]
    if values["action"] not in ACTION_LABELS and values["action"] not in HOLD_LABELS:
        values["action"] = ""
    if values["status"] not in AnalysisJob.Status.values:
        values["status"] = ""
    for key in ("date_from", "date_to"):
        try:
            if not parse_date(values[key]):
                values[key] = ""
        except ValueError:
            values[key] = ""
    return values


def filter_jobs(qs, filters: dict):
    if filters.get("q"):
        q = filters["q"]
        qs = qs.filter(Q(title__icontains=q) | Q(video__icontains=q))
    if filters.get("action"):
        qs = qs.filter(predictions__action_label=filters["action"]).distinct()
    if filters.get("status"):
        qs = qs.filter(status=filters["status"])
    if filters.get("date_from"):
        qs = qs.filter(created_at__date__gte=parse_date(filters["date_from"]))
    if filters.get("date_to"):
        qs = qs.filter(created_at__date__lte=parse_date(filters["date_to"]))
    return qs
