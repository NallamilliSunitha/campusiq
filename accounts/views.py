# accounts/views.py  ✅ FULL UPDATED FILE (your same file, only updated request_permission + added email helper + imports)

from datetime import timedelta

from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from .models import UserProfile, PasswordResetOTP
from permissions.models import PermissionRequest, RequestHistory
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.conf import settings
from django.utils import timezone
from django.core.mail import send_mail

from django.db.models import Exists, OuterRef, Case, When, Value, IntegerField
from django.db.models import Max



from .models import PasswordResetOTP
import random



# -------------------- AUTH / REGISTER -------------------- #

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

        user = User.objects.create_user(
            username=username,
            password=password,
            first_name=first_name,
            last_name=last_name,
            email=email,
        )

        UserProfile.objects.create(user=user, role=role, department=department)

        messages.success(request, "Account created successfully!")
        return redirect("login_home")

    return render(request, "accounts/register.html")


def login_home(request):
    return render(request, "accounts/login_home.html")




def _role_login(request, required_roles, template_name):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        # 1️⃣ Check if user exists
        user_obj = User.objects.filter(username=username).first()

        if not user_obj:
            return render(request, template_name, {
                "error": "User not registered. Please register first."
            })

        # 2️⃣ Check password
        user = authenticate(request, username=username, password=password)

        if user is None:
            return render(request, template_name, {
                "error": "Incorrect password."
            })

        # 3️⃣ Check role
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
    return _role_login(request, ["staff", "proctor", "hod", "dean"], "accounts/employee_login.html")


# -------------------- DASHBOARD -------------------- #

@login_required
def dashboard(request):
    user = request.user
    profile = UserProfile.objects.filter(user=user).first()
    role = (profile.role or "").strip().lower() if profile else ""

    roll_number = user.first_name or user.username
    if role == "student" and profile and getattr(profile, "roll_number", None):
        roll_number = profile.roll_number

    submitted_requests = (
        PermissionRequest.objects
        .filter(student=user)
        .select_related("request_to")
        .order_by("-applied_at")
    )

    

    received_requests = (
        PermissionRequest.objects
        .filter(request_to=user)
        .select_related("student")
        .annotate(
        is_urgent_rank=Case(
            When(is_urgent=True, status="pending", then=Value(0)),  # urgent pending first
            When(status="pending", then=Value(1)),                  # normal pending next
            When(status="approved", then=Value(2)),
            When(status="rejected", then=Value(3)),
            default=Value(9),
            output_field=IntegerField(),
        ),
        was_auto_escalated=Exists(
            RequestHistory.objects.filter(
                request_id=OuterRef("pk"),
                action="auto_escalated"
            )
        ),
    )
    .order_by("is_urgent_rank", "-was_auto_escalated", "-applied_at")
)


    submitted_counts = {
        "total": submitted_requests.count(),
        "pending": submitted_requests.filter(status="pending").count(),
        "approved": submitted_requests.filter(status="approved").count(),
        "rejected": submitted_requests.filter(status="rejected").count(),
    }

    received_counts = {"pending": 0, "approved": 0, "rejected": 0}
    if role != "student":
        received_counts["approved"] = received_requests.filter(status="approved").count()
        received_counts["rejected"] = received_requests.filter(status="rejected").count()
        received_counts["pending"] = received_requests.filter(status="pending", current_level=role).count()

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


# -------------------- EMAIL HELPER (NEW) -------------------- #

def _full_name_or_username(u):
    full = (f"{u.first_name} {u.last_name}").strip()
    return full if full else (u.username or "User")


def _send_assigned_email(req):
    """
    ✅ Sends email to the assigned authority when a NEW permission request is created/assigned.
    """
    if not req.request_to:
        return

    to_email = (req.request_to.email or "").strip()
    if not to_email:
        return  # authority has no email saved

    request_id = req.request_code or f"REQ-{req.id:06d}"
    authority_name = _full_name_or_username(req.request_to)
    student_name = _full_name_or_username(req.student)
    title = (req.title or "Permission Request").strip()

    subject = f"[{request_id}] New Permission Request Assigned"

    message = (
        f"Hello {authority_name},\n\n"
        f"A new permission request has been assigned to you for review.\n\n"
        f"Request ID : {request_id}\n"
        f"Student    : {student_name} ({req.student.username})\n"
        f"Title      : {title}\n"
        f"From Date  : {req.from_date}\n"
        f"To Date    : {req.to_date}\n"
        f"Urgent     : {'YES' if req.is_urgent else 'NO'}\n"
        f"Status     : {req.status.upper()}\n\n"
        f"Please login to CampusIQ and review it from your dashboard.\n\n"
        f"Regards,\n"
        f"CampusIQ Team"
    )

    # IMPORTANT: keep fail_silently=False while testing so you can see the real error in console
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[to_email],
        fail_silently=False,
    )


# -------------------- REQUEST PERMISSION (UPDATED) -------------------- #

@login_required
def request_permission(request):
    profile = request.user.userprofile
    my_role = (profile.role or "").strip().lower()

    if my_role == "student":
        roles = ["proctor", "staff", "hod", "dean", "principal"]
    elif my_role in ("staff", "proctor"):
        roles = ["hod", "dean", "principal"]
    elif my_role == "hod":
        roles = ["dean", "principal"]
    elif my_role == "dean":
        roles = ["principal"]
    else:
        roles = []

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

        max_id = PermissionRequest.objects.aggregate(Max("id"))["id__max"] or 0
        next_id = max_id + 1
        request_code = f"REQ-{next_id:06d}"

        is_urgent = request.POST.get("is_urgent") == "on"
        urgent_minutes = request.POST.get("urgent_minutes")

        if is_urgent:
            try:
                m = int(urgent_minutes or 0)
            except:
                m = getattr(settings, "URGENT_MIN_MINUTES", 10)

            m = max(getattr(settings, "URGENT_MIN_MINUTES", 10),
                    min(getattr(settings, "URGENT_MAX_MINUTES", 360), m))
            escalate_at = timezone.now() + timedelta(minutes=m)
        else:
            escalate_at = timezone.now() + timedelta(hours=getattr(settings, "NORMAL_ESCALATION_HOURS", 24))

        req = PermissionRequest.objects.create(
            student=request.user,
            request_to=selected_user,
            request_code=request_code,
            title=request.POST.get("title") or "",
            reason=request.POST.get("reason") or "",
            from_date=request.POST.get("from_date"),
            to_date=request.POST.get("to_date"),
            current_level=target_role,
            file=request.FILES.get("permission_file"),
            is_urgent=is_urgent,
            escalate_at=escalate_at,
        )

        RequestHistory.objects.create(
            request=req,
            action="created",
            from_role=my_role,
            to_role=target_role,
            actor=request.user,
            note="Request created"
        )

        # ✅ NEW: send email to assigned person
        _send_assigned_email(req)

        return redirect("dashboard")

    return render(request, "permissions/permission.html", {
        "users_by_role": users_by_role,
        "profile": profile,
        "today": timezone.localdate(),  # useful for date min in template
    })


# -------------------- MY REQUESTS -------------------- #

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


# -------------------- FILE TEXT EXTRACT -------------------- #

from PyPDF2 import PdfReader
import docx

def extract_text_from_file(uploaded_file):
    """
    Returns extracted text from pdf/doc/docx.
    If extraction fails, returns empty string.
    """
    if not uploaded_file:
        return ""

    name = uploaded_file.name.lower()

    try:
        if name.endswith(".pdf"):
            reader = PdfReader(uploaded_file)
            text = []
            for page in reader.pages:
                text.append(page.extract_text() or "")
            return "\n".join(text).strip()

        if name.endswith(".docx"):
            d = docx.Document(uploaded_file)
            return "\n".join([p.text for p in d.paragraphs]).strip()

        if name.endswith(".doc"):
            return ""

    except Exception:
        return ""

    return ""
def forgot_password(request):
    if request.method == "POST":
        username = request.POST.get("username")

        user = User.objects.filter(username=username).first()

        if not user:
            return render(request, "accounts/forgot_password.html", {
                "error": "User not registered."
            })

        otp = str(random.randint(100000, 999999))

        # delete old OTPs
        PasswordResetOTP.objects.filter(user=user).delete()

        PasswordResetOTP.objects.create(
            user=user,
            otp=otp
        )

        send_mail(
            subject="CampusIQ Password Reset OTP",
            message=f"Your OTP is: {otp}\n\nValid for 5 minutes.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False
        )

        request.session["reset_user"] = user.id

        return redirect("verify_otp")

    return render(request, "accounts/forgot_password.html")
def verify_otp(request):
    user_id = request.session.get("reset_user")

    if not user_id:
        return redirect("forgot_password")

    user = User.objects.get(id=user_id)

    if request.method == "POST":
        entered_otp = request.POST.get("otp")

        otp_obj = PasswordResetOTP.objects.filter(user=user).first()

        if not otp_obj:
            return render(request, "accounts/verify_otp.html", {
                "error": "OTP not found."
            })

        if otp_obj.is_expired():
            otp_obj.delete()
            return render(request, "accounts/verify_otp.html", {
                "error": "OTP expired."
            })

        if otp_obj.otp != entered_otp:
            return render(request, "accounts/verify_otp.html", {
                "error": "Invalid OTP."
            })

        return redirect("reset_password")

    return render(request, "accounts/verify_otp.html")
def reset_password(request):
    user_id = request.session.get("reset_user")

    if not user_id:
        return redirect("forgot_password")

    user = User.objects.get(id=user_id)

    if request.method == "POST":
        password = request.POST.get("password")
        confirm = request.POST.get("confirm_password")

        if password != confirm:
            return render(request, "accounts/reset_password.html", {"error": "Passwords do not match."
    })

        user.save()

        PasswordResetOTP.objects.filter(user=user).delete()
        del request.session["reset_user"]

        return redirect("login_home")

    return render(request, "accounts/reset_password.html")
