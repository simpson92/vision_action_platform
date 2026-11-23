"""DRF API: 분석 요청 CRUD + 상태 조회.

- 일반 회원은 자기 작업만 조회·수정·삭제 (queryset 자체를 본인 것으로 제한 → 남의 id는 404)
- 관리자(is_staff)는 전체 조회 가능
- 작업 등록은 DB 커밋이 끝난 뒤(transaction.on_commit) Celery에 보내 "작업이 아직 없음" 경쟁을 막음
"""
from django.db import transaction
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from .models import AnalysisJob
from .serializers import AnalysisJobSerializer, AnalysisJobUpdateSerializer, AnalysisStatusSerializer
from .tasks import run_analysis


class AnalysisJobViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = AnalysisJob.objects.select_related("user").prefetch_related("predictions")
        if self.request.user.is_staff and self.request.query_params.get("all") == "1":
            return qs
        return qs.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.action == "partial_update":
            return AnalysisJobUpdateSerializer
        if self.action == "status":
            return AnalysisStatusSerializer
        return AnalysisJobSerializer

    def perform_create(self, serializer):
        job = serializer.save(user=self.request.user)

        def enqueue():
            result = run_analysis.delay(job.pk)
            AnalysisJob.objects.filter(pk=job.pk).update(celery_task_id=result.id or "")

        transaction.on_commit(enqueue)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        # 분석이 끝날 때까지 기다리지 않고 작업 ID를 바로 돌려줍니다.
        return Response({"id": serializer.instance.pk, "status": serializer.instance.status}, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=["post"])
    def clear(self, request):
        """내 분석 이력 전체 삭제. 관리자라도 본인 것만 지우고, 처리 중인 작업은 남깁니다."""
        jobs = AnalysisJob.objects.filter(user=request.user).exclude(status=AnalysisJob.Status.STARTED)
        videos = [job.video for job in jobs if job.video]
        deleted_ids = list(jobs.values_list("pk", flat=True))
        jobs.delete()
        for video in videos:
            video.delete(save=False)
        skipped = AnalysisJob.objects.filter(user=request.user).count()
        return Response({"deleted": len(deleted_ids), "deleted_ids": deleted_ids, "skipped": skipped})

    def perform_destroy(self, instance):
        # 사람별 예측은 FK CASCADE로 함께 삭제, 영상 파일도 지웁니다. 처리 중인 작업은 지우지 않습니다.
        if instance.status == AnalysisJob.Status.STARTED:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("처리 중인 작업은 끝난 뒤에 삭제할 수 있습니다.")
        video = instance.video
        instance.delete()
        if video:
            video.delete(save=False)

    @action(detail=True, methods=["get"])
    def status(self, request, pk=None):
        job = self.get_object()
        return Response(AnalysisStatusSerializer(job).data)
