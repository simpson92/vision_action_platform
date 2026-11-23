from django.contrib import admin

from .models import AnalysisJob, PersonPrediction


class PersonPredictionInline(admin.TabularInline):
    model = PersonPrediction
    extra = 0
    can_delete = False
    fields = ("track_id", "action_label", "raw_label", "confidence", "margin", "valid_frames", "input_quality")
    readonly_fields = fields


@admin.register(AnalysisJob)
class AnalysisJobAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "input_type", "status", "expected_action", "prediction_summary", "processing_ms", "created_at")
    list_filter = ("status", "input_type", "expected_action", "created_at")
    search_fields = ("user__username", "title", "memo", "celery_task_id")
    readonly_fields = ("celery_task_id", "started_at", "completed_at", "created_at", "processing_ms", "video_duration_sec")
    inlines = [PersonPredictionInline]
    date_hierarchy = "created_at"

    @admin.display(description="사람별 결과")
    def prediction_summary(self, obj):
        return ", ".join(f"#{p.track_id} {p.action_label}" for p in obj.predictions.all()) or "-"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user").prefetch_related("predictions")


@admin.register(PersonPrediction)
class PersonPredictionAdmin(admin.ModelAdmin):
    list_display = ("id", "job", "track_id", "action_label", "confidence", "margin", "input_quality", "predicted_at")
    list_filter = ("action_label", "input_quality", "job__input_type")
    search_fields = ("job__user__username", "action_label")
    list_select_related = ("job",)
