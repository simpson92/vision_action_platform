from django.db import migrations, models


def fill_user_seq(apps, schema_editor):
    """기존 기록에 사용자별 번호를 만든 순서대로 1, 2, 3… 붙입니다."""
    AnalysisJob = apps.get_model("analyses", "AnalysisJob")
    counters = {}
    for job in AnalysisJob.objects.order_by("user_id", "created_at", "id").only("id", "user_id"):
        counters[job.user_id] = counters.get(job.user_id, 0) + 1
        AnalysisJob.objects.filter(pk=job.pk).update(user_seq=counters[job.user_id])


class Migration(migrations.Migration):

    dependencies = [
        ("analyses", "0002_video_meta_and_details"),
    ]

    operations = [
        migrations.AddField(
            model_name="analysisjob",
            name="user_seq",
            field=models.PositiveIntegerField(default=0, editable=False, verbose_name="내 분석 번호"),
        ),
        migrations.RunPython(fill_user_seq, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="analysisjob",
            constraint=models.UniqueConstraint(fields=("user", "user_seq"), name="unique_seq_per_user"),
        ),
    ]
