from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden

from .models import UserProfile
from permissions.models import PermissionRequest, RequestHistory
from datetime import timedelta
from django.conf import settings
from django.utils import timezone


from accounts.models import UserProfile

def register(request):
    if request.method == "POST":
        first_name = request.POST.get("first_name")
        last_name = request.POST.get("last_name")
        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")
        role = request.POST.get("role")
        department = request.POST.get("department")

        if User.objects.filter(username=username).exists():
            messages.error(request, "Roll number already exists!")
            return redirect("register")

        # Create user
        email = request.POST.get("email")
        user = User.objects.create_user(
            username=username,
            password=password,
            first_name=first_name,
            last_name=last_name,
            email=email,
        )

        # Create UserProfile
        UserProfile.objects.create(user=user, role=role, department=department)

        messages.success(request, "Account created successfully!")

        # ✅ IMPORTANT: redirect to 3-cards login page
        return redirect("login_home")

    return render(request, "accounts/register.html")


def login_home(request):
    # shows 3 cards in one page
    return render(request, "accounts/login_home.html")


def _role_login(request, required_roles, template_name):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)
        if user is None:
            return render(request, template_name, {"error": "Invalid credentials"})

        profile = UserProfile.objects.filter(user=user).first()
        role = (profile.role or "").strip().lower() if profile else ""

        if role not in required_roles:
            return HttpResponseForbidden("Wrong login page for your role")

        login(request, user)
        return redirect("dashboard")

    return render(request, template_name)


def student_login(request):
    return _role_login(request, ["student"], "accounts/student_login.html")


def principal_login(request):
    return _role_login(request, ["principal"], "accounts/principal_login.html")


def employee_login(request):
    # everything except student & principal
    return _role_login(request, ["staff", "proctor", "hod", "dean"], "accounts/employee_login.html")


@login_required
def dashboard(request):
    user = request.user
    profile = UserProfile.objects.filter(user=user).first()

    role = (profile.role or "").strip().lower() if profile else ""

    # roll number (optional, kept)
    roll_number = user.first_name or user.username
    if role == "student" and profile and profile.roll_number:
        roll_number = profile.roll_number

    # Submitted requests by this user (newest first)
    submitted_requests = (
        PermissionRequest.objects
        .filter(student=user)
        .select_related("request_to")
        .order_by("-applied_at")
    )

    # Requests assigned to logged-in user (newest first)
    received_requests = (
        PermissionRequest.objects
        .filter(request_to=user)
        .select_related("student")
        .order_by("-applied_at")
    )

    # Counts for submitted requests
    submitted_counts = {
        "total": submitted_requests.count(),
        "pending": submitted_requests.filter(status="pending").count(),
        "approved": submitted_requests.filter(status="approved").count(),
        "rejected": submitted_requests.filter(status="rejected").count(),
    }

    # Counts for received requests
    received_counts = {"pending": 0, "approved": 0, "rejected": 0}
    if role != "student":
        received_counts["approved"] = received_requests.filter(status="approved").count()
        received_counts["rejected"] = received_requests.filter(status="rejected").count()

        # Pending Review: only those still at my level
        received_counts["pending"] = received_requests.filter(
            status="pending",
            current_level=role
        ).count()

    context = {
        "profile": profile,
        "roll_number": roll_number,
        "submitted_requests": submitted_requests,
        "received_requests": received_requests,
        "total": submitted_counts["total"],
        "pending": submitted_counts["pending"],
        "approved": submitted_counts["approved"],
        "rejected": submitted_counts["rejected"],
        "received_counts": received_counts,
    }

    return render(request, "dashboard/dashboard.html", context)


@login_required
def request_permission(request):
    profile = request.user.userprofile
    my_role = (profile.role or "").strip().lower()

    # Determine roles current user can request permission from
    if my_role == "student":
        roles = ["proctor", "staff", "hod", "dean", "principal"]
    elif my_role in ("staff", "proctor"):
        roles = ["hod", "dean", "principal"]
    elif my_role == "hod":
        roles = ["dean", "principal"]
    elif my_role == "dean":
        roles = ["principal"]
    else:  # principal or unknown
        roles = []

    # Users by allowed roles (same department)
    users_by_role = {
        role: list(
            UserProfile.objects.filter(role=role, department=profile.department)
            .select_related("user")
            .values("user__id", "user__first_name", "user__last_name", "user__username")
        )
        for role in roles
    }

    if request.method == "POST":
        selected_user_id = request.POST.get("request_to")
        if not selected_user_id:
            return redirect("request_permission")

        selected_user = User.objects.get(id=selected_user_id)

        target_profile = UserProfile.objects.filter(user=selected_user).first()
        if not target_profile:
            return HttpResponseForbidden("Selected user has no profile")

        target_role = (target_profile.role or "").strip().lower()

        # ✅ Urgent settings (student can pick minutes)
        is_urgent = request.POST.get("is_urgent") == "on"
        urgent_minutes = request.POST.get("urgent_minutes")  # input name in HTML

        # ✅ compute escalate_at
        if is_urgent:
            try:
                m = int(urgent_minutes or 0)
            except:
                m = settings.URGENT_MIN_MINUTES

            m = max(settings.URGENT_MIN_MINUTES, min(settings.URGENT_MAX_MINUTES, m))
            escalate_at = timezone.now() + timedelta(minutes=m)
        else:
            escalate_at = timezone.now() + timedelta(hours=getattr(settings, "NORMAL_ESCALATION_HOURS", 24))

        # ✅ Create request
        req = PermissionRequest.objects.create(
            student=request.user,
            request_to=selected_user,
            title=request.POST.get("title") or "",
            reason=request.POST.get("reason") or "",
            from_date=request.POST.get("from_date"),
            to_date=request.POST.get("to_date"),
            current_level=target_role,      # ✅ always ROLE
            file=request.FILES.get("permission_file"),

            # ✅ new escalation fields
            is_urgent=is_urgent,
            escalate_at=escalate_at,
        )

        # ✅ History entry (for Track)
        RequestHistory.objects.create(
            request=req,
            action="created",
            from_role=my_role,
            to_role=target_role,
            actor=request.user,
            note="Request created"
        )

        return redirect("dashboard")

    return render(request, "permissions/permission.html", {"users_by_role": users_by_role})


@login_required
def my_requests(request):
    user = request.user

    requests = (
        PermissionRequest.objects
        .filter(student=user)
        .select_related("request_to")
        .order_by("-applied_at")
    )

    return render(request, "dashboard/my_requests.html", {"requests": requests})
