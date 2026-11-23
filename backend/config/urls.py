from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("", include("analyses.urls")),
    path("favicon.ico", RedirectView.as_view(url=settings.STATIC_URL + "favicon.svg")),
]

# 업로드 영상 재생용 (개발·시연 환경)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
