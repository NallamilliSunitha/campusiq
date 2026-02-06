from django.urls import path
from . import views

urlpatterns = [
    path("register/", views.register, name="register"),

    # ✅ Login home (3 cards) should be the default login page
    path("login/", views.login_home, name="login_home"),

    # ✅ Role-based logins
    path("student-login/", views.student_login, name="student_login"),
    path("employee-login/", views.employee_login, name="employee_login"),
    path("principal-login/", views.principal_login, name="principal_login"),

    # ✅ After login
    path("dashboard/", views.dashboard, name="dashboard"),

    # ✅ Permission pages
    path("request_permission/", views.request_permission, name="request_permission"),
    path("my-requests/", views.my_requests, name="my_requests"),
]
