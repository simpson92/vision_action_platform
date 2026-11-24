from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class AccountTests(TestCase):
    def test_signup_logs_in_and_redirects(self):
        r = self.client.post(reverse("signup"), {"username": "alice", "password1": "Vision!2026pw", "password2": "Vision!2026pw"})
        self.assertRedirects(r, reverse("analyses:index"))
        self.assertTrue(User.objects.filter(username="alice").exists())

    def test_login_and_logout(self):
        User.objects.create_user("bob", password="Vision!2026pw")
        r = self.client.post(reverse("login"), {"username": "bob", "password": "Vision!2026pw"})
        self.assertRedirects(r, reverse("analyses:index"))
        self.client.post(reverse("logout"))
        self.assertEqual(self.client.get(reverse("analyses:index")).status_code, 302)

    def test_anonymous_cannot_use_pages_or_api(self):
        self.assertRedirects(self.client.get(reverse("analyses:index")), f"{reverse('login')}?next=/")
        self.assertIn(self.client.get("/api/analyses/").status_code, (401, 403))

    def test_member_can_change_password(self):
        user = User.objects.create_user("carol", password="Vision!2026pw")
        self.client.force_login(user)
        url = reverse("password_change")
        self.assertEqual(self.client.get(url).status_code, 200)
        bad = self.client.post(url, {"old_password": "wrong", "new_password1": "New!Vision2026", "new_password2": "New!Vision2026"})
        self.assertEqual(bad.status_code, 200)  # 현재 비밀번호가 틀리면 바뀌지 않음
        r = self.client.post(url, {"old_password": "Vision!2026pw", "new_password1": "New!Vision2026", "new_password2": "New!Vision2026"})
        self.assertRedirects(r, reverse("analyses:index"))
        self.assertEqual(self.client.get(reverse("analyses:index")).status_code, 200)  # 바꾼 뒤에도 로그인 유지
        user.refresh_from_db()
        self.assertTrue(user.check_password("New!Vision2026"))
