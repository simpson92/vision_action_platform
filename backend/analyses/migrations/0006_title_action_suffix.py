from django.db import migrations

ACTION_LABELS = {
    "bend_return": "허리 굽혔다 펴기",
    "leg_raise_lower": "다리 들었다 내리기",
    "walk_turn_walk": "걷다가 방향 바꿔 걷기",
    "drink_return": "마시고 제자리로",
    "sit_stand": "앉았다 일어나기",
    "wave": "손 흔들기",
}
SUFFIXES = (".mp4", ".avi", ".mov", ".mkv", ".webm")


def add_action(apps, schema_editor):
    """파일 이름만 있는 예전 제목 뒤에 동작 이름을 괄호로 붙입니다.
    고른 동작이 있으면 그것을, 없으면 Confidence가 가장 높은 사람의 예측을 씁니다."""
    AnalysisJob = apps.get_model("analyses", "AnalysisJob")
    for job in AnalysisJob.objects.all():
        title = job.title or ""
        if not (title.lower().endswith(SUFFIXES) or (title.startswith("IP Webcam · 카메라") and "(" not in title)):
            continue
        if job.expected_action in ACTION_LABELS:
            name = ACTION_LABELS[job.expected_action]
        else:
            top = job.predictions.order_by("-confidence").first()
            if top is None:
                continue
            name = ACTION_LABELS.get(top.action_label, "판단 보류" if top.action_label == "UNCERTAIN" else "인식 불가")
        job.title = f"{title} ({name})"[:100]
        job.save(update_fields=["title"])


class Migration(migrations.Migration):
    dependencies = [("analyses", "0005_fill_empty_titles")]
    operations = [migrations.RunPython(add_action, migrations.RunPython.noop)]
