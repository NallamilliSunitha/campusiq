from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST

from accounts.models import UserProfile
from .models import PermissionRequest, RequestHistory
from django.core.mail import send_mail
from django.conf import settings 
from django.core.mail import send_mail
from django.conf import settings

def notify_student(req, action_text):
    student_email = req.student.email
    if not student_email:
        return  # no email saved

    subject = f"Your permission request is {action_text.upper()}"
    msg = (
        f"Hi {req.student.username},\n\n"
        f"Your request '{req.title}' has been {action_text.upper()}.\n\n"
        f"Current Level: {req.current_level}\n"
    )

    send_mail(
        subject,
        msg,
        settings.DEFAULT_FROM_EMAIL,
        [student_email],
        fail_silently=False
    )




@login_required
def index(request):
    return render(request, 'permissions/index.html')

@login_required
def view_request(request, id):
    req = get_object_or_404(PermissionRequest, id=id)
    return render(request, 'permissions/view_request.html', {'req': req})


from .models import RequestHistory  # make sure this import exists

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
    # logic later (HOD / Principal)
    return redirect('dashboard')
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from accounts.models import UserProfile
from .models import PermissionRequest

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

    # students cannot forward
    if my_role == "student":
        return JsonResponse({"error": "student blocked"}, status=403)

    # only the assigned user can forward
    if req.request_to_id != request.user.id:
        return JsonResponse(
            {"error": f"not assigned (req_to={req.request_to_id}, me={request.user.id})"},
            status=403
        )

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

    # ❌ students cannot forward
    if my_role == "student":
        return JsonResponse({"ok": False, "error": "Students cannot forward"}, status=403)

    # ❌ only the currently assigned user can forward
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

    # ✅ THIS IS THE IMPORTANT PART (UPDATE + HISTORY)
    req.request_to = target_profile.user
    req.status = "pending"
    req.current_level = target_profile.role   # 🔥 fixes dashboard current location
    req.save()
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


    RequestHistory.objects.create(
        request=req,
        action="forwarded",
        from_role=my_role,
        to_role=target_profile.role,
        actor=request.user,
        note="Forwarded"
    )

    return JsonResponse({"ok": True})

@login_required
def track_request(request, id):
    req = get_object_or_404(PermissionRequest, id=id)

    # student can track only their own request
    if req.student_id != request.user.id:
        return HttpResponseForbidden("Not allowed")

    history = RequestHistory.objects.filter(request=req).order_by("created_at")

    return render(request, "permissions/track_request.html", {
        "request_obj": req,
        "history": history
    })