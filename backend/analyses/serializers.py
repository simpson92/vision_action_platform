"""입력 검증과 JSON 표현.

- 업로드: 확장자·용량 확인. IP Webcam: 허용 목록의 카메라 번호만 받음.
- 상태·AI 결과는 읽기 전용이라 사용자가 PATCH로 바꿀 수 없습니다(제목·메모만 수정).
"""
from pathlib import Path

from django.conf import settings
from rest_framework import serializers

from .models import AnalysisJob, PersonPrediction

ALLOWED_VIDEO_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv", ".webm"}


class PersonPredictionSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(read_only=True)

    class Meta:
        model = PersonPrediction
        fields = ("track_id", "action_label", "action_display", "raw_label", "confidence", "margin",
                  "probabilities", "details", "window_count", "valid_frames", "input_quality", "start_sec", "end_sec")
        read_only_fields = fields


class AnalysisJobSerializer(serializers.ModelSerializer):
    predictions = PersonPredictionSerializer(many=True, read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    input_type_display = serializers.CharField(source="get_input_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    video_url = serializers.SerializerMethodField()
    total_seconds = serializers.FloatField(read_only=True)

    class Meta:
        model = AnalysisJob
        fields = ("id", "username", "title", "memo", "input_type", "input_type_display", "video", "video_url",
                  "camera_index", "capture_seconds", "expected_action", "status", "status_display",
                  "celery_task_id", "error_message", "result_message", "video_duration_sec", "video_meta", "processing_ms",
                  "total_seconds", "created_at", "started_at", "completed_at", "predictions")
        read_only_fields = ("status", "celery_task_id", "error_message", "result_message", "video_duration_sec", "video_meta",
                            "processing_ms", "created_at", "started_at", "completed_at", "capture_seconds")
        extra_kwargs = {"video": {"write_only": True, "required": False}}

    def get_video_url(self, obj):
        return obj.video.url if obj.video else None

    def validate_video(self, video):
        if video is None:
            return video
        if Path(video.name).suffix.lower() not in ALLOWED_VIDEO_SUFFIXES:
            raise serializers.ValidationError("MP4 등 영상 파일만 올릴 수 있습니다.")
        if video.size > settings.MAX_UPLOAD_MB * 1024 * 1024:
            raise serializers.ValidationError(f"영상은 {settings.MAX_UPLOAD_MB}MB 이하만 올릴 수 있습니다.")
        return video

    def validate(self, attrs):
        if self.instance is not None:
            return attrs  # 수정은 제목·메모만 (UpdateSerializer 사용)
        input_type = attrs.get("input_type")
        if input_type == AnalysisJob.InputType.UPLOAD:
            if not attrs.get("video"):
                raise serializers.ValidationError({"video": "분석할 영상을 선택해 주세요."})
            attrs.pop("camera_index", None)
        elif input_type == AnalysisJob.InputType.IP_WEBCAM:
            cameras = settings.IP_WEBCAM_ALLOWED_URLS
            if not cameras:
                raise serializers.ValidationError({"camera_index": "서버에 허용된 IP Webcam이 없습니다(.env의 IP_WEBCAM_ALLOWED_URLS)."})
            index = attrs.get("camera_index")
            if index is None:
                index = 0
            if not 0 <= index < len(cameras):
                raise serializers.ValidationError({"camera_index": "허용 목록에 없는 카메라입니다."})
            attrs["camera_index"] = index
            attrs.pop("video", None)
            attrs["capture_seconds"] = settings.IP_WEBCAM_CAPTURE_SECONDS
        return attrs


class AnalysisJobUpdateSerializer(serializers.ModelSerializer):
    """PATCH: 제목·메모만 바꿀 수 있습니다."""

    class Meta:
        model = AnalysisJob
        fields = ("title", "memo")


class AnalysisStatusSerializer(serializers.ModelSerializer):
    """GET /api/analyses/{id}/status/: 브라우저가 주기적으로 묻는 가벼운 응답."""

    predictions = PersonPredictionSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    is_finished = serializers.BooleanField(read_only=True)
    total_seconds = serializers.FloatField(read_only=True)
    input_type_display = serializers.CharField(source="get_input_type_display", read_only=True)
    video_name = serializers.SerializerMethodField()
    video_url = serializers.SerializerMethodField()

    class Meta:
        model = AnalysisJob
        fields = ("id", "title", "status", "status_display", "is_finished", "error_message", "result_message",
                  "input_type", "input_type_display", "video_name", "video_url", "expected_action", "video_duration_sec",
                  "video_meta", "processing_ms", "total_seconds", "created_at", "predictions")

    def get_video_url(self, obj):
        return obj.video.url if obj.video else None

    def get_video_name(self, obj):
        return Path(obj.video.name).name if obj.video else None
