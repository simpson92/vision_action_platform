"""과제 테스트 T05~T09 중 웹 쪽: 비동기 등록, 영구 저장, CRUD 권한, 관리자, 예외 처리.

FastAPI 호출은 가짜 응답으로 바꿔(mock) Django·Celery 로직만 확인합니다.
"""
import shutil
import tempfile
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import AnalysisJob, PersonPrediction
from .services import AIServiceError
from .tasks import run_analysis

MEDIA = tempfile.mkdtemp()

FAKE_RESULT = {
    "status": "ok", "message": None, "processing_ms": 1234,
    "video": {"duration_sec": 2.5, "fps": 25.0, "frame_count": 62, "width": 640, "height": 480},
    "predictions": [
        {"track_id": 1, "action_label": "bend_return", "raw_label": "bend_return", "confidence": 0.28, "margin": 0.07,
         "probabilities": {"bend_return": 0.28}, "window_count": 3, "valid_frames": 62, "input_quality": "good",
         "window_agreement": 0.67, "detected_frames": 60, "interpolated_joints": 4, "mean_keypoint_conf": 0.81,
         "timeline": [{"start_sec": 0.0, "end_sec": 2.0, "label": "bend_return", "probabilities": {"bend_return": 0.3}}],
         "start_sec": 0.0, "end_sec": 2.4},
        {"track_id": 2, "action_label": "UNCERTAIN", "raw_label": "wave", "confidence": 0.22, "margin": 0.01,
         "probabilities": {"wave": 0.22}, "window_count": 3, "valid_frames": 40, "input_quality": "fair"},
    ],
}


def video_file(name="clip.mp4"):
    return SimpleUploadedFile(name, b"\x00\x00\x00\x18ftypmp42", content_type="video/mp4")


@override_settings(MEDIA_ROOT=MEDIA, CELERY_TASK_ALWAYS_EAGER=True, IP_WEBCAM_ALLOWED_URLS=["http://cam.local/video"])
class AnalysisApiTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.a = User.objects.create_user("a", password="pw-Vision-1")
        self.b = User.objects.create_user("b", password="pw-Vision-1")
        self.admin = User.objects.create_user("boss", password="pw-Vision-1", is_staff=True, is_superuser=True)

    def create_job(self, user, **kwargs):
        defaults = {"input_type": "upload", "video": video_file()}
        defaults.update(kwargs)
        return AnalysisJob.objects.create(user=user, **defaults)

    # T05: 요청 직후 작업 ID 반환, 커밋 후 Celery 등록
    @mock.patch("analyses.views.run_analysis.delay")
    def test_create_returns_job_id_immediately(self, delay):
        delay.return_value.id = "task-123"
        self.client.force_login(self.a)
        with self.captureOnCommitCallbacks(execute=True):
            r = self.client.post("/api/analyses/", {"input_type": "upload", "video": video_file()})
        self.assertEqual(r.status_code, 202)
        job = AnalysisJob.objects.get(pk=r.json()["id"])
        self.assertEqual(job.status, "PENDING")
        delay.assert_called_once_with(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.celery_task_id, "task-123")

    def test_upload_requires_video_and_valid_extension(self):
        self.client.force_login(self.a)
        self.assertEqual(self.client.post("/api/analyses/", {"input_type": "upload"}).status_code, 400)
        bad = SimpleUploadedFile("note.txt", b"hi", content_type="text/plain")
        self.assertEqual(self.client.post("/api/analyses/", {"input_type": "upload", "video": bad}).status_code, 400)

    def test_ip_webcam_only_allowed_camera(self):
        self.client.force_login(self.a)
        r = self.client.post("/api/analyses/", {"input_type": "ip_webcam", "camera_index": 5})
        self.assertEqual(r.status_code, 400)

    # T06: 결과가 DB에 저장되고 새로 불러와도 남아 있음
    @mock.patch("analyses.tasks.predict_video", return_value=FAKE_RESULT)
    def test_task_saves_predictions(self, _):
        job = self.create_job(self.a)
        run_analysis.apply(args=[job.pk])
        job.refresh_from_db()
        self.assertEqual(job.status, "SUCCESS")
        self.assertEqual(job.processing_ms, 1234)
        self.assertEqual(PersonPrediction.objects.filter(job=job).count(), 2)
        self.client.force_login(self.a)
        body = self.client.get(f"/api/analyses/{job.pk}/status/").json()
        self.assertTrue(body["is_finished"])
        self.assertEqual([p["track_id"] for p in body["predictions"]], [1, 2])
        # 영상별 판단 근거(그래프용)도 저장·응답
        self.assertEqual(body["video_meta"]["frame_count"], 62)
        details = body["predictions"][0]["details"]
        self.assertEqual(details["window_agreement"], 0.67)
        self.assertEqual(details["timeline"][0]["label"], "bend_return")
        self.assertEqual(body["predictions"][1]["details"], {})

    # T09: 잘못된 파일 → 실패 상태와 사유 저장
    @mock.patch("analyses.tasks.predict_video", side_effect=AIServiceError("영상을 열 수 없습니다."))
    def test_task_failure_is_saved(self, _):
        job = self.create_job(self.a)
        run_analysis.apply(args=[job.pk])
        job.refresh_from_db()
        self.assertEqual(job.status, "FAILURE")
        self.assertIn("영상을 열 수 없습니다", job.error_message)

    @mock.patch("analyses.tasks.capture_clip", side_effect=__import__("analyses.camera_capture", fromlist=["CameraError"]).CameraError("카메라에 연결하지 못했습니다."))
    def test_camera_failure_is_saved(self, _):
        job = AnalysisJob.objects.create(user=self.a, input_type="ip_webcam", camera_index=0, capture_seconds=8)
        run_analysis.apply(args=[job.pk])
        job.refresh_from_db()
        self.assertEqual(job.status, "FAILURE")
        self.assertIn("카메라", job.error_message)

    # T07: A는 B의 작업을 조회·수정·삭제할 수 없음
    def test_user_cannot_touch_others_job(self):
        job_b = self.create_job(self.b)
        self.client.force_login(self.a)
        self.assertEqual(self.client.get(f"/api/analyses/{job_b.pk}/").status_code, 404)
        self.assertEqual(self.client.patch(f"/api/analyses/{job_b.pk}/", {"memo": "x"}, content_type="application/json").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/analyses/{job_b.pk}/").status_code, 404)
        self.assertEqual(self.client.get(reverse("analyses:detail", args=[job_b.pk])).status_code, 404)
        self.assertEqual(self.client.get("/api/analyses/").json()["count"], 0)

    def test_patch_only_changes_title_and_memo(self):
        job = self.create_job(self.a)
        self.client.force_login(self.a)
        r = self.client.patch(f"/api/analyses/{job.pk}/", {"memo": "좋음", "status": "SUCCESS"}, content_type="application/json")
        self.assertEqual(r.status_code, 200)
        job.refresh_from_db()
        self.assertEqual(job.memo, "좋음")
        self.assertEqual(job.status, "PENDING")

    @mock.patch("analyses.tasks.predict_video", return_value=FAKE_RESULT)
    def test_delete_removes_predictions(self, _):
        job = self.create_job(self.a)
        run_analysis.apply(args=[job.pk])
        self.client.force_login(self.a)
        self.assertEqual(self.client.delete(f"/api/analyses/{job.pk}/").status_code, 204)
        self.assertFalse(PersonPrediction.objects.filter(job_id=job.pk).exists())

    @mock.patch("analyses.tasks.predict_video", return_value=FAKE_RESULT)
    def test_clear_deletes_only_my_finished_jobs(self, _):
        done = self.create_job(self.a)
        run_analysis.apply(args=[done.pk])
        running = self.create_job(self.a)
        AnalysisJob.objects.filter(pk=running.pk).update(status="STARTED")
        other = self.create_job(self.b)
        self.client.force_login(self.a)
        res = self.client.post("/api/analyses/clear/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["deleted_ids"], [done.pk])
        self.assertTrue(AnalysisJob.objects.filter(pk=running.pk).exists())
        self.assertTrue(AnalysisJob.objects.filter(pk=other.pk).exists())
        self.assertFalse(PersonPrediction.objects.filter(job_id=done.pk).exists())

    # T08: 관리자만 대시보드·전체 목록
    @mock.patch("analyses.tasks.predict_video", return_value=FAKE_RESULT)
    def test_dashboard_admin_only(self, _):
        run_analysis.apply(args=[self.create_job(self.a).pk])
        self.client.force_login(self.a)
        self.assertEqual(self.client.get(reverse("analyses:dashboard")).status_code, 302)
        self.client.force_login(self.admin)
        r = self.client.get(reverse("analyses:dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["action_chart"]["values"][0], 1)  # bend_return 1건
        self.assertEqual(self.client.get("/api/analyses/?all=1").json()["count"], 1)
        self.assertEqual(self.client.get("/admin/analyses/analysisjob/").status_code, 200)

    def test_index_page_renders(self):
        self.client.force_login(self.a)
        r = self.client.get(reverse("analyses:index"))
        self.assertContains(r, "AI 분석 시작")
        self.assertContains(r, "카메라 1")
        self.assertNotContains(r, "cam.local")  # 카메라 주소는 화면에 노출하지 않음

    # IP Webcam 미리보기: 허용 목록 번호로만, 서버가 사진을 대신 받아 전달 (주소 비노출)
    @mock.patch("analyses.page_views.requests.get")
    def test_camera_snapshot_proxy(self, get):
        get.return_value.content = b"\xff\xd8jpeg"
        get.return_value.headers = {"Content-Type": "image/jpeg"}
        get.return_value.raise_for_status.return_value = None
        url = reverse("analyses:camera_snapshot", args=[0])
        self.assertEqual(self.client.get(url).status_code, 302)  # 로그인 필요
        self.client.force_login(self.a)
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, b"\xff\xd8jpeg")
        get.assert_called_once_with("http://cam.local/shot.jpg", timeout=mock.ANY)
        self.assertEqual(self.client.get(reverse("analyses:camera_snapshot", args=[3])).status_code, 404)

