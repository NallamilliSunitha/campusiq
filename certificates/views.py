from io import BytesIO
import os
import qrcode

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader

from accounts.models import UserProfile
from .models import CertificateRequest, IssuedCertificate, StudentMark, CertificateAttachment


# ---------------- HELPERS ---------------- #

def _full_name(u):
    s = (u.get_full_name() or "").strip()
    return s if s else u.username


def _get_profile(user):
    return UserProfile.objects.filter(user=user).first()


def _role(user):
    p = _get_profile(user)
    return (p.role or "").strip().lower() if p else ""


def _is_dean(user):
    return _role(user) == "dean"


def _can_review(user):
    return _role(user) in ("dean", "principal")


def _dean_for_department(dept):
    p = UserProfile.objects.filter(role__iexact="dean", department=dept).select_related("user").first()
    return p.user if p else None


def _principal_for_department(dept):
    p = UserProfile.objects.filter(role__iexact="principal", department=dept).select_related("user").first()
    return p.user if p else None


def _send_mail(to_email, subject, body):
    if to_email:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to_email], fail_silently=True)


def _email_text_request(req, event, extra=""):
    assigned = _full_name(req.request_to) if req.request_to else "N/A"
    return (
        f"Hello {_full_name(req.student)},\n\n"
        f"Certificate Request Update: {event}\n"
        f"Request ID: {req.request_code}\n"
        f"Certificate Type: {req.get_cert_type_display()}\n"
        f"Status: {req.status.upper()}\n"
        f"Assigned To: {assigned}\n"
        f"Created On: {timezone.localtime(req.created_at).strftime('%Y-%m-%d %H:%M')}\n"
        f"{extra}\n\n"
        f"Regards,\nCampusIQ"
    ).strip()


def _certificate_wording(req):
    student = req.student
    p = UserProfile.objects.filter(user=student).first()
    dept = p.department if p else "—"

    name = (student.get_full_name() or student.username).strip()
    roll = student.username

    if req.cert_type == "study":
        return f"This is to certify that {name} (Roll No: {roll}) is a bonafide student of the Department of {dept} and is currently studying in our institution."

    if req.cert_type == "bonafide":
        return f"This is to certify that {name} (Roll No: {roll}) is a bonafide student of the Department of {dept}. This certificate is issued based on institutional records."

    if req.cert_type == "tc":
        return f"This is to certify that {name} (Roll No: {roll}) has applied for Transfer Certificate. This certificate is issued as per institutional records."

    if req.cert_type == "marks_memo":
        return f"This is to certify that the marks memo belongs to {name} (Roll No: {roll}). The marks shown are as per official records."

    return "This certificate is issued as per institutional records."


def _build_certificate_context(req, issued):
    student_profile = UserProfile.objects.filter(user=req.student).first()
    dept = student_profile.department if student_profile else ""

    approver_profile = None
    if issued and issued.approved_by:
        approver_profile = UserProfile.objects.filter(user=issued.approved_by).first()

    attachments = req.attachments.all().order_by("-uploaded_at")

    return {
        "req": req,
        "issued": issued,
        "student_profile": student_profile,
        "department": dept,
        "today": timezone.localtime(timezone.now()).date(),
        "wording": _certificate_wording(req),
        "approver_profile": approver_profile,
        "attachments": attachments,
        "qr_url": f"/certificates/qr/{issued.cert_code}/" if issued else "",
        "verify_url": f"/certificates/verify/{issued.cert_code}/" if issued else "",
    }


# ---------------- STUDENT / STAFF ---------------- #

@login_required
def apply_certificate(request):
    profile = _get_profile(request.user)
    dept = profile.department if profile else ""
    dean_user = _dean_for_department(dept)

    if not dean_user:
        return HttpResponseForbidden("Dean not found for your department")

    if request.method == "POST":
        cert_type = (request.POST.get("cert_type") or "").strip()
        purpose = (request.POST.get("purpose") or "").strip()

        valid_types = {"study", "bonafide", "tc", "marks_memo"}
        if cert_type not in valid_types:
            return render(request, "certificates/apply_certificate.html", {
                "error": "Please select a valid certificate type.",
                "profile": profile,
                "dean": dean_user,
            })

        if cert_type == "marks_memo" and not StudentMark.objects.filter(student=request.user).exists():
            return render(request, "certificates/apply_certificate.html", {
                "error": "Marks are not available. Please contact exam cell.",
                "profile": profile,
                "dean": dean_user,
            })

        req = CertificateRequest.objects.create(
            cert_type=cert_type,
            student=request.user,
            request_to=dean_user,
            purpose=purpose,
            status="pending",
        )

        # supporting files
        for f in request.FILES.getlist("supporting_files"):
            CertificateAttachment.objects.create(request=req, file=f)

        # emails
        _send_mail(
            request.user.email,
            f"Certificate request submitted ({req.request_code})",
            _email_text_request(req, "REQUEST SUBMITTED")
        )

        _send_mail(
            dean_user.email,
            f"New certificate request assigned ({req.request_code})",
            (
                f"Hello {_full_name(dean_user)},\n\n"
                f"A new certificate request has been assigned to you.\n"
                f"Request ID: {req.request_code}\n"
                f"Student: {_full_name(req.student)} ({req.student.username})\n"
                f"Certificate: {req.get_cert_type_display()}\n\n"
                f"Regards,\nCampusIQ"
            )
        )

        return redirect("my_certificates")

    return render(request, "certificates/apply_certificate.html", {
        "profile": profile,
        "dean": dean_user,
    })


@login_required
def my_certificates(request):
    qs = CertificateRequest.objects.filter(student=request.user).select_related("request_to").order_by("-created_at")
    return render(request, "certificates/my_certificates.html", {"requests": qs})


# ---------------- DEAN / PRINCIPAL ---------------- #

@login_required
def received_certificate_requests(request):
    if not _can_review(request.user):
        return HttpResponseForbidden("Only Dean/Principal can access")

    qs = CertificateRequest.objects.filter(request_to=request.user).select_related("student").order_by("-created_at")
    return render(request, "certificates/authority_inbox.html", {
        "requests": qs,
        "profile": _get_profile(request.user),
    })


@login_required
def review_certificate_request(request, id):
    if not _can_review(request.user):
        return HttpResponseForbidden("Only Dean/Principal can review")

    req = get_object_or_404(CertificateRequest, id=id)

    # ✅ FIX: your model uses request_to (not assigned_to)
    if req.request_to_id != request.user.id:
        return HttpResponseForbidden("Not assigned to you")

    attachments = req.attachments.all().order_by("-uploaded_at")

    return render(request, "certificates/review_certificate.html", {
        "req": req,
        "attachments": attachments
    })



@login_required
def forward_certificate_to_principal(request, id):
    if not _is_dean(request.user):
        return HttpResponseForbidden("Only Dean can forward to Principal")

    req = get_object_or_404(CertificateRequest, id=id)
    if req.request_to_id != request.user.id:
        return HttpResponseForbidden("Not assigned to you")

    if req.status != "pending":
        return redirect("received_certificate_requests")

    dean_profile = _get_profile(request.user)
    dept = dean_profile.department if dean_profile else ""
    principal_user = _principal_for_department(dept)

    if not principal_user:
        return HttpResponse("Principal not found for your department", status=404)

    req.request_to = principal_user
    req.save(update_fields=["request_to", "updated_at"])

    _send_mail(
        req.student.email,
        f"Certificate request forwarded ({req.request_code})",
        _email_text_request(req, "FORWARDED", extra="Forwarded to Principal for final approval.")
    )

    _send_mail(
        principal_user.email,
        f"Certificate request assigned ({req.request_code})",
        (
            f"Hello {_full_name(principal_user)},\n\n"
            f"A certificate request was forwarded to you for approval.\n"
            f"Request ID: {req.request_code}\n"
            f"Student: {_full_name(req.student)} ({req.student.username})\n"
            f"Certificate: {req.get_cert_type_display()}\n\n"
            f"Regards,\nCampusIQ"
        )
    )

    return redirect("received_certificate_requests")


@login_required
def approve_certificate_request(request, id):
    if not _can_review(request.user):
        return HttpResponseForbidden("Only Dean/Principal can approve")

    req = get_object_or_404(CertificateRequest, id=id)
    if req.request_to_id != request.user.id:
        return HttpResponseForbidden("Not assigned to you")

    if req.status != "pending":
        return redirect("received_certificate_requests")

    req.status = "approved"
    req.save(update_fields=["status", "updated_at"])

    issued, _ = IssuedCertificate.objects.get_or_create(request=req)
    issued.approved_by = request.user
    issued.approved_at = timezone.now()
    issued.save()

    _send_mail(
        req.student.email,
        f"Certificate Approved ({req.request_code})",
        _email_text_request(req, "APPROVED", extra=f"Certificate Code: {issued.cert_code}")
    )

    return redirect("received_certificate_requests")


@login_required
def reject_certificate_request(request, id):
    if not _can_review(request.user):
        return HttpResponseForbidden("Only Dean/Principal can reject")

    req = get_object_or_404(CertificateRequest, id=id)
    if req.request_to_id != request.user.id:
        return HttpResponseForbidden("Not assigned to you")

    if req.status != "pending":
        return redirect("received_certificate_requests")

    req.status = "rejected"
    req.save(update_fields=["status", "updated_at"])

    _send_mail(
        req.student.email,
        f"Certificate Rejected ({req.request_code})",
        _email_text_request(req, "REJECTED")
    )

    return redirect("received_certificate_requests")


# ---------------- VIEW / VERIFY / QR / PDF ---------------- #

@login_required
def view_certificate(request, id):
    req = get_object_or_404(CertificateRequest, id=id)

    role = _role(request.user)
    if req.student_id != request.user.id and req.request_to_id != request.user.id and role not in ("dean", "principal"):
        return HttpResponseForbidden("Not allowed")

    issued = IssuedCertificate.objects.filter(request=req).select_related("approved_by").first()
    if not issued or req.status != "approved":
        return HttpResponse("Certificate will be visible only after approval.", status=400)

    ctx = _build_certificate_context(req, issued)
    return render(request, "certificates/certificate_view.html", ctx)


def verify_certificate(request, code):
    issued = IssuedCertificate.objects.filter(cert_code=code).select_related("request", "request__student", "approved_by").first()
    return render(request, "certificates/verify.html", {"issued": issued})


def certificate_qr(request, code):
    verify_url = request.build_absolute_uri(f"/certificates/verify/{code}/")
    img = qrcode.make(verify_url)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return HttpResponse(buf.getvalue(), content_type="image/png")


@login_required
def download_certificate_pdf(request, id):
    req = get_object_or_404(CertificateRequest, id=id)

    role = _role(request.user)
    if req.student_id != request.user.id and req.request_to_id != request.user.id and role not in ("dean", "principal"):
        return HttpResponseForbidden("Not allowed")

    issued = IssuedCertificate.objects.filter(request=req).select_related("approved_by").first()
    if not issued or req.status != "approved":
        return HttpResponse("Certificate not approved yet", status=400)

    approver_profile = None
    if issued.approved_by:
        approver_profile = UserProfile.objects.filter(user=issued.approved_by).first()

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawCentredString(width / 2, height - 70, "CAMPUSIQ - OFFICIAL CERTIFICATE")

    pdf.setFont("Helvetica", 11)
    y = height - 120
    pdf.drawString(60, y, f"Certificate Code: {issued.cert_code}"); y -= 18
    pdf.drawString(60, y, f"Student: {_full_name(req.student)} ({req.student.username})"); y -= 18
    pdf.drawString(60, y, f"Certificate Type: {req.get_cert_type_display()}"); y -= 25

    # Body
    text_obj = pdf.beginText(60, y)
    text_obj.setFont("Helvetica", 11)
    for line in _certificate_wording(req).split(". "):
        line = line.strip()
        if line:
            if not line.endswith("."):
                line += "."
            text_obj.textLine(line)
    pdf.drawText(text_obj)

    # Signature / Stamp
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(60, 170, f"Approved By: {_full_name(issued.approved_by) if issued.approved_by else '—'}")
    pdf.setFont("Helvetica", 10)
    if issued.approved_at:
        pdf.drawString(60, 155, f"Approved At: {timezone.localtime(issued.approved_at).strftime('%Y-%m-%d %H:%M')}")

    # Try to draw signature + stamp if they exist in UserProfile (ImageField)
    # Expected fields: approver_profile.signature, approver_profile.stamp  (change if your field names differ)
    if approver_profile:
        try:
            if getattr(approver_profile, "signature", None) and approver_profile.signature.name:
                sig_path = os.path.join(settings.MEDIA_ROOT, approver_profile.signature.name)
                if os.path.exists(sig_path):
                    pdf.drawImage(ImageReader(sig_path), 60, 95, width=160, height=60, mask='auto')
        except Exception:
            pass

        try:
            if getattr(approver_profile, "stamp", None) and approver_profile.stamp.name:
                stamp_path = os.path.join(settings.MEDIA_ROOT, approver_profile.stamp.name)
                if os.path.exists(stamp_path):
                    pdf.drawImage(ImageReader(stamp_path), width - 190, 90, width=120, height=120, mask='auto')
        except Exception:
            pass

    # QR
    try:
        verify_url = request.build_absolute_uri(f"/certificates/verify/{issued.cert_code}/")
        img = qrcode.make(verify_url)
        qr_buf = BytesIO()
        img.save(qr_buf, format="PNG")
        qr_buf.seek(0)
        pdf.drawImage(ImageReader(qr_buf), width - 165, 25, width=110, height=110, mask='auto')
        pdf.setFont("Helvetica", 8)
        pdf.drawString(width - 165, 15, "Scan to verify")
    except Exception:
        pass

    pdf.showPage()
    pdf.save()

    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{issued.cert_code}.pdf"'
    return response
