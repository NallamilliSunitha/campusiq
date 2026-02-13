"""campusiq URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
import accounts.views as views


urlpatterns = [
    path('admin/', admin.site.urls),
    path('permissions/', include('permissions.urls')),
    path('accounts/', include('accounts.urls')),
    path('auth/', include('django.contrib.auth.urls')),
    path("certificates/", include("certificates.urls")),
    path("", TemplateView.as_view(template_name="index.html"), name="home"),
    path("forgot-password/", views.forgot_password, name="forgot_password"),
    path("verify-otp/", views.verify_otp, name="verify_otp"),
    path("reset-password/", views.reset_password, name="reset_password"),



  # your app URLs
      # Django auth URLs now at /auth/
]

from django.conf import settings
from django.conf.urls.static import static

if settings.DEBUG and settings.MEDIA_URL:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)