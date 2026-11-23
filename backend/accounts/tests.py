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
