from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from .models import UserProfile
from django.contrib import messages
from django.contrib.auth import authenticate, login
from permissions.models import PermissionRequest
from django.contrib.auth.decorators import login_required
from django.db.models import Count


def register(request):
    if request.method == "POST":
        first_name = request.POST.get("first_name")
        last_name = request.POST.get("last_name")
        username = request.POST.get("username")
        password = request.POST.get("password")
        role = request.POST.get("role")
        department = request.POST.get("department")

        if User.objects.filter(username=username).exists():
            messages.error(request, "Roll number already exists!")
            return redirect('register')

        # Create user
        user = User.objects.create_user(username=username, password=password,
                                        first_name=first_name, last_name=last_name)
        
        # Create UserProfile
        UserProfile.objects.create(user=user, role=role, department=department)

        messages.success(request, "Account created successfully!")
        return redirect('login')

    return render(request, "accounts/register.html")


def login_view(request):
    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            return render(request, 'accounts/login.html', {'error': 'Invalid credentials'})
    return render(request, 'accounts/login.html')






@login_required
def dashboard(request):
    user = request.user
    profile = UserProfile.objects.filter(user=user).first()

    role = (profile.role or "").strip().lower() if profile else ""

    # roll number (optional, kept)
    roll_number = user.first_name or user.username
    if role == "student" and profile and profile.roll_number:
        roll_number = profile.roll_number

    # ✅ Student submitted requests (newest first)
    submitted_requests = (
        PermissionRequest.objects
        .filter(student=user)
        .select_related("request_to")
        .order_by("-applied_at")
    )

    # ✅ Requests assigned to logged-in user (newest first)
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

    # Counts for received requests (staff/proctor/hod/principal)
    received_counts = {"pending": 0, "approved": 0, "rejected": 0}
    if role != "student":
        status_data = received_requests.values("status").annotate(count=Count("status"))
        for item in status_data:
            received_counts[item["status"]] = item["count"]

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
    profile = request.user.userprofile  # current user's profile

    # Determine roles the current user can request permission from
    if profile.role == "student":
        roles = ['proctor', 'staff', 'hod', 'principal']
    elif profile.role == "staff":
        roles = ['hod', 'principal']
    elif profile.role == "hod":
        roles = ['principal']
    else:  # principal or any other role
        roles = []

    # Get users by allowed roles
    users_by_role = {
        role: list(
            UserProfile.objects.filter(role=role)
            .values('user__id', 'user__first_name', 'user__last_name')
        )
        for role in roles
    }

    if request.method == "POST":
        selected_user_id = request.POST.get("request_to")
        selected_user = User.objects.get(id=selected_user_id)

        PermissionRequest.objects.create(
            student=request.user,
            request_to=selected_user,
            title=request.POST.get("title"),
            reason=request.POST.get("reason"),
            from_date=request.POST.get("from_date"),
            to_date=request.POST.get("to_date"),
            current_level=selected_user.username,
            file=request.FILES.get("permission_file")
        )

        return redirect("dashboard")

    context = {
        "users_by_role": users_by_role
    }
    return render(request, "permissions/permission.html", context)




