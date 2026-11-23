from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
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


class MeView(APIView):
    """GET /accounts/me/: 로그인한 사용자 정보 (DRF)."""

    def get(self, request):
        user = request.user
        return Response({"id": user.id, "username": user.username, "is_staff": user.is_staff})
