from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.forms import UserCreationForm
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView
from rest_framework.response import Response
from rest_framework.views import APIView


class SignUpView(CreateView):
    """회원가입 후 바로 로그인해 분석 화면으로 보냅니다. Django 기본 User를 사용합니다."""

    form_class = UserCreationForm
    template_name = "accounts/signup.html"
    success_url = reverse_lazy("analyses:index")

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response


class PasswordChangeView(SuccessMessageMixin, auth_views.PasswordChangeView):
    """일반 회원이 직접 비밀번호 변경. 현재 비밀번호 확인 후 바꾸고, 로그인은 그대로 유지됩니다(Django 기본 동작)."""

    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("analyses:index")
    success_message = "비밀번호를 바꿨습니다. 다음 로그인부터 새 비밀번호를 쓰세요."


class MeView(APIView):
    """GET /accounts/me/: 로그인한 사용자 정보 (DRF)."""

    def get(self, request):
        user = request.user
        return Response({"id": user.id, "username": user.username, "is_staff": user.is_staff})
