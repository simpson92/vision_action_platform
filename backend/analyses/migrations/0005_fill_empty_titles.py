from pathlib import Path

from django.db import migrations


def fill_titles(apps, schema_editor):
    """제목이 비어 있는 예전 작업에 영상 파일 이름(또는 카메라 번호)을 넣습니다."""
    AnalysisJob = apps.get_model("analyses", "AnalysisJob")
    for job in AnalysisJob.objects.filter(title=""):
        if job.video:
            job.title = Path(job.video.name).name[:100]
        elif job.camera_index is not None:
            job.title = f"IP Webcam · 카메라 {job.camera_index + 1}"
        else:
            continue
        job.save(update_fields=["title"])


class Migration(migrations.Migration):
    dependencies = [("analyses", "0004_pose_overlay")]
    operations = [migrations.RunPython(fill_titles, migrations.RunPython.noop)]
