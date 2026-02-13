from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django.db import transaction

from accounts.models import UserProfile
from .models import PermissionRequest, RequestHistory

import os


# ---------------- HELPERS ---------------- #

def _full_name_or_username(u):
    full = (f"{u.first_name} {u.last_name}").strip()
    return full if full else (u.username or "User")


def notify_student(req, event, *, actor=None, to_user=None, extra_note=None):
    """
    Sends professional email to student for events:
      - received, forwarded, approved, rejected, auto_escalated
    """
    request_id = getattr(req, "request_code", None) or f"REQ-{req.id:06d}"
    title = (req.title or "").strip() or "Permission Request"
    student_name = _full_name_or_username(req.student)

    student_email = (req.student.email or "").strip()
    if not student_email:
        return

    authority_name = _full_name_or_username(req.request_to) if req.request_to else "N/A"
    action_by = _full_name_or_username(actor) if actor else "System"

    date_from = getattr(req, "from_date", None)
    date_to = getattr(req, "to_date", None)
    date_range = f"{date_from} to {date_to}" if (date_from and date_to) else "—"

    status = (req.status or "").upper()
    current_level = (req.current_level or "").upper()

    subject_map = {
        "received":       f"[{request_id}] New Permission Request Submitted",
        "forwarded":      f"[{request_id}] Permission Request Forwarded",
        "approved":       f"[{request_id}] Permission Request Approved",
        "rejected":       f"[{request_id}] Permission Request Rejected",
        "auto_escalated": f"[{request_id}] Permission Request Auto-Escalated",
    }

    subject = subject_map.get(event, f"[{request_id}] Permission Request Update")

    lines = [
        f"Hello {student_name},",
        "",
        "This is an update regarding your permission request.",
        "",
        f"Request ID   : {request_id}",
        f"Title        : {title}",
        f"Date Range   : {date_range}",
        f"Status       : {status}",
        f"Current Level: {current_level}",
        f"Assigned To  : {authority_name}",
    ]

    if event == "received":
        lines += ["", "Your request has been successfully submitted and assigned for review."]

    elif event == "forwarded":
        to_user_name = _full_name_or_username(to_user) if to_user else "Next Authority"
        lines += ["", f"Your request has been forwarded to: {to_user_name}.", f"Forwarded By: {action_by}"]

    elif event == "approved":
        lines += ["", "Your request has been approved.", f"Approved By: {action_by}"]

    elif event == "rejected":
        lines += ["", "Your request has been rejected.", f"Rejected By: {action_by}"]

    elif event == "auto_escalated":
        to_user_name = _full_name_or_username(to_user) if to_user else authority_name
        lines += [
            "",
            "Your urgent request was not acted upon within the specified time, so it has been auto-escalated.",
            f"Escalated To: {to_user_name}",
        ]

    if extra_note:
        lines += ["", f"Note: {extra_note}"]

    lines += ["", "Regards,", "CampusIQ Team"]

    send_mail(
        subject=subject,
        message="\n".join(lines),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[student_email],
        fail_silently=False,
    )


def notify_assignee(req, event, *, actor=None, from_user=None, extra_note=None):
    """
    ✅ Sends email to assigned authority (req.request_to) when:
      - event="assigned"  -> new request created
      - event="forwarded" -> request forwarded to this authority
    """
    if not req.request_to:
        return

    to_email = (req.request_to.email or "").strip()
    if not to_email:
        return  # no email saved for assignee

    request_id = getattr(req, "request_code", None) or f"REQ-{req.id:06d}"
    title = (req.title or "").strip() or "Permission Request"

    authority_name = _full_name_or_username(req.request_to)
    student_name = _full_name_or_username(req.student)

    date_from = getattr(req, "from_date", None)
    date_to = getattr(req, "to_date", None)
    date_range = f"{date_from} to {date_to}" if (date_from and date_to) else "—"

    action_by = _full_name_or_username(actor) if actor else "System"
    from_name = _full_name_or_username(from_user) if from_user else student_name

    if event == "assigned":
        subject = f"[{request_id}] New Permission Request Assigned"
        body_lines = [
            f"Hello {authority_name},",
            "",
            "A new permission request has been assigned to you for review.",
            "",
            f"Request ID : {request_id}",
            f"Student    : {student_name} ({req.student.username})",
            f"Title      : {title}",
            f"Date Range : {date_range}",
            "",
            "Please login to CampusIQ and take action.",
        ]
    else:  # forwarded
        subject = f"[{request_id}] Permission Request Forwarded to You"
        body_lines = [
            f"Hello {authority_name},",
            "",
            "A permission request has been forwarded to you for review.",
            "",
            f"Request ID  : {request_id}",
            f"Student     : {student_name} ({req.student.username})",
            f"Title       : {title}",
            f"Date Range  : {date_range}",
            f"Forwarded By: {action_by}",
            f"From        : {from_name}",
            "",
            "Please login to CampusIQ and take action.",
        ]

    if extra_note:
        body_lines += ["", f"Note: {extra_note}"]

    body_lines += ["", "Regards,", "CampusIQ Team"]

    send_mail(
        subject=subject,
        message="\n".join(body_lines),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[to_email],
        fail_silently=False,
    )


# ---------------- BASIC VIEWS ---------------- #

@login_required
def index(request):
    return render(request, "permissions/index.html")


def extract_text_from_uploaded_file(file_field):
    """
    Returns (text, error_message)
    """
    if not file_field:
        return ("", None)

    try:
        path = file_field.path
    except Exception:
        return ("", "File path not available.")

    ext = os.path.splitext(path)[1].lower()

    if ext == ".docx":
        try:
            import docx
            doc = docx.Document(path)
            text = "\n".join([p.text for p in doc.paragraphs]).strip()
            return (text, None if text else "DOCX has no readable text.")
        except Exception as e:
            return ("", f"Could not read DOCX: {e}")

    if ext == ".pdf":
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(path)
            parts = []
            for page in reader.pages:
                parts.append((page.extract_text() or "").strip())
            text = "\n\n".join([p for p in parts if p]).strip()
            if not text:
                return ("", "This PDF looks like scanned/image-based, so text can't be extracted (OCR needed).")
            return (text, None)
        except Exception as e:
            return ("", f"Could not read PDF: {e}")

    if ext == ".doc":
        return ("", "Old .DOC format can't be extracted directly. Upload .DOCX or PDF text file.")

    return ("", f"Unsupported file type: {ext}")


@login_required
def view_request(request, id):
    req = get_object_or_404(PermissionRequest, id=id)

    display_reason = req.reason or ""
    extract_error = None

    if req.file and req.file.name:
        # You can extract & show file text if needed
        pass

    return render(request, "permissions/view_request.html", {
        "req": req,
        "display_reason": display_reason,
        "extract_error": extract_error,
    })


# ---------------- APPROVE / REJECT ---------------- #

@login_required
def approve_request(request, id):
    req = get_object_or_404(PermissionRequest, id=id)
    req.status = "approved"
    req.save()

    if req.student.email:
        send_mail(
            subject="Your permission request is APPROVED",
            message=f"Hi {req.student.username},\n\nYour request '{req.title}' has been APPROVED.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[req.student.email],
            fail_silently=True
        )

    return redirect("dashboard")


@login_required
def reject_request(request, id):
    req = get_object_or_404(PermissionRequest, id=id)
    req.status = "rejected"
    req.save()

    if req.student.email:
        send_mail(
            subject="Your permission request is REJECTED",
            message=f"Hi {req.student.username},\n\nYour request '{req.title}' has been REJECTED.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[req.student.email],
            fail_silently=True
        )

    return redirect("dashboard")


@login_required
def forward_request(request, id):
    req = get_object_or_404(PermissionRequest, id=id)
    return redirect("dashboard")


# ---------------- FORWARD UI / FORWARD DO ---------------- #

ROLE_FLOW = {
    "student": ["proctor", "staff", "hod", "dean", "principal"],
    "proctor": ["hod", "dean", "principal"],
    "staff": ["hod", "dean", "principal"],
    "hod": ["dean", "principal"],
    "dean": ["principal"],
    "principal": [],
}


@login_required
def forward_ui(request, pk):
    req = get_object_or_404(PermissionRequest, pk=pk)

    my_profile = UserProfile.objects.filter(user=request.user).first()
    if not my_profile:
        return JsonResponse({"error": "no profile"}, status=403)

    my_role = (my_profile.role or "").strip().lower()

    if my_role == "student":
        return JsonResponse({"error": "student blocked"}, status=403)

    if req.request_to_id != request.user.id:
        return JsonResponse({"error": "not assigned"}, status=403)

    my_dept = my_profile.department
    allowed_roles = ROLE_FLOW.get(my_role, [])

    selected_role = (request.GET.get("role") or "").strip().lower()

    users = []
    if selected_role and selected_role in allowed_roles:
        qs = UserProfile.objects.filter(
            role=selected_role,
            department=my_dept
        ).select_related("user")
        users = list(qs.values("user__id", "user__username", "user__first_name", "user__last_name"))

    return JsonResponse({"allowed_roles": allowed_roles, "users": users})


@login_required
@require_POST
def forward_do(request, pk):
    req = get_object_or_404(PermissionRequest, pk=pk)

    my_profile = UserProfile.objects.filter(user=request.user).first()
    if not my_profile:
        return JsonResponse({"ok": False, "error": "Profile not found"}, status=403)

    my_role = (my_profile.role or "").strip().lower()
    if my_role == "student":
        return JsonResponse({"ok": False, "error": "Students cannot forward"}, status=403)

    if req.request_to_id != request.user.id:
        return JsonResponse({"ok": False, "error": "Not assigned to you"}, status=403)

    my_dept = my_profile.department
    allowed_roles = ROLE_FLOW.get(my_role, [])

    target_role = (request.POST.get("target_role") or "").strip().lower()
    target_user_id = request.POST.get("target_user_id")

    if target_role not in allowed_roles:
        return JsonResponse({"ok": False, "error": "Not allowed role"}, status=403)

    target_profile = UserProfile.objects.filter(
        user_id=target_user_id,
        role=target_role,
        department=my_dept
    ).first()

    if not target_profile:
        return JsonResponse({"ok": False, "error": "User not found in same department/role"}, status=404)

    # ✅ UPDATE REQUEST
    req.request_to = target_profile.user
    req.status = "pending"
    req.current_level = target_profile.role
    req.save()

    # ✅ STUDENT EMAIL (you already had)
    if req.student.email:
        send_mail(
            subject="Your permission request was FORWARDED",
            message=(
                f"Hi {req.student.username},\n\n"
                f"Your request '{req.title}' has been FORWARDED to {target_profile.role.upper()}."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[req.student.email],
            fail_silently=True
        )

    # ✅ NEW: EMAIL TO NEW ASSIGNEE
    notify_assignee(req, "forwarded", actor=request.user, from_user=request.user)

    RequestHistory.objects.create(
        request=req,
        action="forwarded",
        from_role=my_role,
        to_role=target_profile.role,
        actor=request.user,
        note="Forwarded"
    )

    return JsonResponse({"ok": True})


# ---------------- TRACK / DELETE ---------------- #

@login_required
def track_request(request, id):
    req = get_object_or_404(PermissionRequest, id=id)

    if req.student_id != request.user.id:
        return HttpResponseForbidden("Not allowed")

    history = RequestHistory.objects.filter(request=req).order_by("created_at")

    return render(request, "permissions/track_request.html", {
        "request_obj": req,
        "history": history,
    })


@login_required
def delete_request(request, id):
    if request.method != "POST":
        return HttpResponseForbidden("POST only")

    req = get_object_or_404(PermissionRequest, id=id)

    if req.status != "pending":
        return HttpResponseForbidden("Only pending requests can be deleted")

    if req.student_id != request.user.id:
        return HttpResponseForbidden("You can delete only your own requests")

    profile = UserProfile.objects.filter(user=request.user).first()
    my_role = (profile.role or "").strip().lower() if profile else ""

    RequestHistory.objects.create(
        request=req,
        action="rejected",
        from_role=my_role,
        to_role=None,
        actor=request.user,
        note="Deleted by requester"
    )

    req.delete()
    messages.success(request, "Request deleted successfully.")
    return redirect("dashboard")


# ---------------- BULK FORWARD ---------------- #

@login_required
@require_POST
def bulk_forward_do(request):
    my_profile = UserProfile.objects.filter(user=request.user).first()
    if not my_profile:
        return JsonResponse({"ok": False, "error": "Profile not found"}, status=403)

    my_role = (my_profile.role or "").strip().lower()
    if my_role == "student":
        return JsonResponse({"ok": False, "error": "Students cannot forward"}, status=403)

    my_dept = my_profile.department
    allowed_roles = ROLE_FLOW.get(my_role, [])

    target_role = (request.POST.get("target_role") or "").strip().lower()
    target_user_id = request.POST.get("target_user_id")

    ids = request.POST.getlist("request_ids")
    ids = [int(x) for x in ids if str(x).isdigit()]

    if not ids:
        return JsonResponse({"ok": False, "error": "No requests selected"}, status=400)

    if target_role not in allowed_roles:
        return JsonResponse({"ok": False, "error": "Not allowed role"}, status=403)

    target_profile = UserProfile.objects.filter(
        user_id=target_user_id,
        role=target_role,
        department=my_dept
    ).select_related("user").first()

    if not target_profile:
        return JsonResponse({"ok": False, "error": "Target user not found in same dept/role"}, status=404)

    new_role = (target_profile.role or "").strip().lower()
    action_label = "forwarded"

    qs = PermissionRequest.objects.filter(
        id__in=ids,
        request_to=request.user,
        status="pending"
    )

    updated = 0
    skipped = []

    with transaction.atomic():
        for req in qs.select_related("student"):
            req.request_to = target_profile.user
            req.current_level = new_role
            req.status = "pending"
            req.save(update_fields=["request_to", "current_level", "status", "updated_at"])

            # ✅ NEW: mail to new assignee (for each forwarded request)
            notify_assignee(req, "forwarded", actor=request.user, from_user=request.user)

            RequestHistory.objects.create(
                request=req,
                action=action_label,
                from_role=my_role,
                to_role=new_role,
                actor=request.user,
                note=f"Forwarded to {target_profile.user.username}"
            )
            updated += 1

        valid_ids = set(qs.values_list("id", flat=True))
        for rid in ids:
            if rid not in valid_ids:
                skipped.append(rid)

    return JsonResponse({
        "ok": True,
        "updated": updated,
        "skipped": skipped,
        "target": target_profile.user.username
    })
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, render
from django.core.mail import send_mail
from django.conf import settings

from accounts.models import UserProfile
from .models import PermissionRequest, RequestHistory

ROLE_FLOW = {
    "student": ["proctor", "staff", "hod", "dean", "principal"],
    "proctor": ["hod", "dean", "principal"],
    "staff": ["hod", "dean", "principal"],
    "hod": ["dean", "principal"],
    "dean": ["principal"],
    "principal": [],
}

def _full_name_or_username(u):
    full = (u.get_full_name() or "").strip()
    return full if full else u.username

def _send_mail(subject, message, to_email):
    if not to_email:
        return
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [to_email], fail_silently=False)


ROLE_FLOW = {
    "student": ["proctor", "staff", "hod", "dean", "principal"],
    "proctor": ["hod", "dean", "principal"],
    "staff": ["hod", "dean", "principal"],
    "hod": ["dean", "principal"],
    "dean": ["principal"],
    "principal": [],
}

def _full_name_or_username(u):
    full = (u.get_full_name() or "").strip()
    return full if full else u.username

def _send_mail(subject, message, to_email):
    if not to_email:
        return
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [to_email], fail_silently=False)


from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from accounts.models import UserProfile
from .models import PermissionRequest
@login_required
def reassign_ui(request, pk):
    req = get_object_or_404(PermissionRequest, pk=pk)

    # only assigned person can reassign
    if req.request_to != request.user:
        return JsonResponse({"ok": False, "error": "Not allowed"}, status=403)

    my_profile = UserProfile.objects.filter(user=request.user).first()
    if not my_profile:
        return JsonResponse({"ok": False, "error": "Profile not found"}, status=403)

    # ✅ Get ALL staff in same department (no role restriction)
    users = UserProfile.objects.filter(
    department=my_profile.department
).exclude(user=request.user).exclude(role="student")


    data = []
    for u in users:
        data.append({
            "id": u.user.id,
            "username": u.user.username,
            "first_name": u.user.first_name,
            "last_name": u.user.last_name,
            "role": u.role,
        })

    return JsonResponse({"ok": True, "users": data})

@login_required
@require_POST
def reassign_do(request, pk):
    req = get_object_or_404(PermissionRequest, pk=pk)

    # Only assigned person can reassign
    if req.request_to != request.user:
        return JsonResponse({"ok": False, "error": "Not allowed"}, status=403)

    # Only pending requests can be reassigned
    if req.status != "pending":
        return JsonResponse({"ok": False, "error": "Only pending requests can be reassigned"}, status=400)

    target_user_id = request.POST.get("target_user_id")
    if not target_user_id:
        return JsonResponse({"ok": False, "error": "No user selected"}, status=400)

    my_profile = UserProfile.objects.filter(user=request.user).first()
    if not my_profile:
        return JsonResponse({"ok": False, "error": "Profile not found"}, status=403)

    # ✅ Ensure SAME DEPARTMENT
    target_profile = UserProfile.objects.filter(
        user_id=target_user_id,
        department=my_profile.department
    ).select_related("user").first()

    if not target_profile:
        return JsonResponse({"ok": False, "error": "User not found in same department"}, status=404)

    # Update request
    req.request_to = target_profile.user
    req.current_level = target_profile.role
    req.save(update_fields=["request_to", "current_level", "updated_at"])

    RequestHistory.objects.create(
        request=req,
        action="reassigned",
        from_role=my_profile.role,
        to_role=target_profile.role,
        actor=request.user,
        note="Reassigned manually"
    )

    return JsonResponse({"ok": True})
