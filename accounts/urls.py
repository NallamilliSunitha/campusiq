from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('request_permission/', views.request_permission, name='request_permission'),
    path("my-requests/", views.my_requests, name="my_requests"),
]
