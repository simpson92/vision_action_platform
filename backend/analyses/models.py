"""업무 테이블 2개: AnalysisJob(분석 요청·상태) 1 : N PersonPrediction(영상 속 사람별 예측).

회원 테이블은 Django 기본 auth_user를 그대로 씁니다.
"""
from django.conf import settings
from django.db import models

ACTION_CHOICES = [
    ("bend_return", "허리 굽혔다 펴기"),
    ("leg_raise_lower", "다리 들었다 내리기"),
    ("walk_turn_walk", "걷다가 방향 바꿔 걷기"),
    ("drink_return", "마시고 제자리로"),
    ("sit_stand", "앉았다 일어나기"),
    ("wave", "손 흔들기"),
]
ACTION_LABELS = dict(ACTION_CHOICES)


class AnalysisJob(models.Model):
    class InputType(models.TextChoices):
        UPLOAD = "upload", "영상 업로드"
        IP_WEBCAM = "ip_webcam", "IP Webcam"

    class Status(models.TextChoices):
        PENDING = "PENDING", "대기"
        STARTED = "STARTED", "처리 중"
        SUCCESS = "SUCCESS", "완료"
        FAILURE = "FAILURE", "실패"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="analysis_jobs")
    title = models.CharField("제목", max_length=100, blank=True)
    memo = models.TextField("메모", blank=True)
    input_type = models.CharField("입력 방식", max_length=20, choices=InputType.choices)
    # 영상 파일은 Media 저장소에 두고 DB에는 경로만 저장합니다.
    video = models.FileField("영상", upload_to="analyses/%Y/%m/%d/", blank=True)
    # IP Webcam은 URL이 아니라 허용 목록의 번호만 저장합니다 (접속정보를 DB·화면에 남기지 않음).
    camera_index = models.PositiveSmallIntegerField("카메라 번호", null=True, blank=True)
    capture_seconds = models.FloatField("수집 시간(초)", null=True, blank=True)
    # 사용자가 "이 동작을 했다"고 고른 값. 검증된 정답 Label이 아닙니다.
    expected_action = models.CharField("수행한 동작(사용자 선택)", max_length=30, choices=ACTION_CHOICES, blank=True)

    status = models.CharField("상태", max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    celery_task_id = models.CharField(max_length=255, blank=True)
    error_message = models.TextField("오류 메시지", blank=True)
    result_message = models.CharField("결과 메시지", max_length=255, blank=True)
    video_duration_sec = models.FloatField(null=True, blank=True)
    # FastAPI가 돌려준 영상 정보(fps, frame_count, width, height)
    video_meta = models.JSONField("영상 정보", default=dict, blank=True)
    processing_ms = models.PositiveIntegerField("AI 처리 시간(ms)", null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "-created_at"])]

    def __str__(self):
        return f"#{self.pk} {self.get_input_type_display()} {self.status}"

    @property
    def is_finished(self):
        return self.status in (self.Status.SUCCESS, self.Status.FAILURE)

    @property
    def top_prediction(self):
        """Confidence가 가장 높은 사람의 예측 (이력 표의 Confidence 칸)."""
        preds = list(self.predictions.all())
        return max(preds, key=lambda p: p.confidence) if preds else None

    @property
    def match_state(self):
        """사용자가 고른 실제 동작과 비교: match / mismatch / hold(판단 보류만 있음) / None(비교 불가)."""
        if not self.expected_action or self.status != self.Status.SUCCESS:
            return None
        labels = [p.action_label for p in self.predictions.all()]
        if not labels:
            return None
        if self.expected_action in labels:
            return "match"
        if all(label in ("UNCERTAIN", "INSUFFICIENT_INPUT") for label in labels):
            return "hold"
        return "mismatch"

    @property
    def total_seconds(self):
        if self.completed_at and self.created_at:
            return round((self.completed_at - self.created_at).total_seconds(), 1)
        return None


class PersonPrediction(models.Model):
    job = models.ForeignKey(AnalysisJob, on_delete=models.CASCADE, related_name="predictions")
    # 한 작업(영상) 안에서만 의미 있는 추적 번호. 영구적인 사람 ID가 아닙니다.
    track_id = models.PositiveIntegerField()
    # 6개 동작 중 하나, 또는 UNCERTAIN(판단 보류) / INSUFFICIENT_INPUT(입력 부족)
    action_label = models.CharField(max_length=30, db_index=True)
    raw_label = models.CharField("기준 적용 전 1등", max_length=30, blank=True)
    confidence = models.FloatField()
    margin = models.FloatField(default=0)
    probabilities = models.JSONField(default=dict, blank=True)
    # 영상별 판단 근거(화면 그래프용): Window별 확률(timeline), 전체 구간/Window 평균 확률,
    # Window 일치율, 사람 검출 Frame 수, 보간한 관절 수, 평균 관절 Confidence
    details = models.JSONField("판단 근거", default=dict, blank=True)
    window_count = models.PositiveIntegerField(default=0)
    valid_frames = models.PositiveIntegerField(default=0)
    input_quality = models.CharField(max_length=10, blank=True)
    start_sec = models.FloatField(null=True, blank=True)
    end_sec = models.FloatField(null=True, blank=True)
    predicted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["job", "track_id"]
        constraints = [models.UniqueConstraint(fields=["job", "track_id"], name="unique_track_per_job")]

    def __str__(self):
        return f"job {self.job_id} / track {self.track_id}: {self.action_label}"

    @property
    def is_decided(self):
        return self.action_label in ACTION_LABELS

    @property
    def action_display(self):
        return ACTION_LABELS.get(self.action_label, {"UNCERTAIN": "판단 보류", "INSUFFICIENT_INPUT": "입력 부족"}.get(self.action_label, self.action_label))
