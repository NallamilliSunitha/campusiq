from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from datetime import timedelta

from permissions.models import PermissionRequest, RequestHistory
from accounts.models import UserProfile


ROLE_FLOW = {
    "student": ["proctor", "staff", "hod", "dean", "principal"],
    "proctor": ["hod", "dean", "principal"],
    "staff": ["hod", "dean", "principal"],
    "hod": ["dean", "principal"],
    "dean": ["principal"],
    "principal": [],
}


def _full_name_or_username(user):
    full = (user.get_full_name() or "").strip()
    return full if full else user.username


def send_request_email(subject, message, to_email, extra_note=None):
    if not to_email:
        return

    final_message = message
    if extra_note:
        final_message = f"{message}\n\nNote:\n{extra_note}"

    send_mail(
        subject=subject,
        message=final_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[to_email],
        fail_silently=True,   # keep like your original
    )


class Command(BaseCommand):
    help = "Warn 10 minutes before urgent escalation + auto escalates pending permission requests based on escalate_at time."

    def handle(self, *args, **options):
        now = timezone.now()
        updated = 0
        warned = 0

        # -------------------------------
        # 1) ✅ 10-minute WARNING MAIL (urgent only)
        # -------------------------------
        warn_window_end = now + timedelta(minutes=10)

        qs_warn = PermissionRequest.objects.filter(
            status="pending",
            is_urgent=True,
            escalate_at__isnull=False,
            escalate_at__gt=now,                  # still not escalated
            escalate_at__lte=warn_window_end,     # within next 10 minutes
            warning_sent_at__isnull=True,         # not warned before
        ).select_related("student", "request_to")

        for req in qs_warn:
            # must have current assignee + email
            if req.request_to and req.request_to.email:
                local_escalate = timezone.localtime(req.escalate_at)
                mins_left = int((req.escalate_at - now).total_seconds() // 60)

                send_request_email(
                    subject=f"[{req.request_code}] URGENT: Auto-escalation in {mins_left} minutes",
                    message=(
                        f"Hello {_full_name_or_username(req.request_to)},\n\n"
                        f"This is a reminder that an URGENT permission request assigned to you will be auto-escalated soon.\n\n"
                        f"Request ID: {req.request_code}\n"
                        f"Title: {req.title}\n"
                        f"Requested by: {_full_name_or_username(req.student)} ({req.student.username})\n"
                        f"From: {req.from_date}  To: {req.to_date}\n"
                        f"Auto-escalation time: {local_escalate.strftime('%Y-%m-%d %H:%M')}\n\n"
                        f"Please take action before escalation.\n\n"
                        f"Regards,\nCampusIQ"
                    ),
                    to_email=req.request_to.email,
                )

                # mark warned (so it sends ONLY ONCE)
                req.warning_sent_at = now
                req.save(update_fields=["warning_sent_at"])
                warned += 1

                # optional history entry
                RequestHistory.objects.create(
                    request=req,
                    action="urgent_warning",
                    from_role=(req.current_level or "").strip().lower(),
                    to_role=(req.current_level or "").strip().lower(),
                    actor=None,
                    note="10-minute urgent escalation warning email sent",
                )

        # -------------------------------
        # 2) ✅ AUTO ESCALATION (your existing)
        # -------------------------------
        qs = PermissionRequest.objects.filter(
            status="pending",
            escalate_at__isnull=False,
            escalate_at__lte=now,
        ).select_related("student", "request_to")

        for req in qs:
            current_role = (req.current_level or "").strip().lower()

            # find next role
            next_roles = ROLE_FLOW.get(current_role, [])
            if not next_roles:
                continue  # no escalation possible

            next_role = next_roles[0]

            # find next user in same dept
            student_profile = UserProfile.objects.filter(user=req.student).first()
            dept = student_profile.department if student_profile else None

            target_profile = UserProfile.objects.filter(
                role=next_role,
                department=dept
            ).select_related("user").first()

            if not target_profile:
                continue

            old_role = current_role
            old_request_to = req.request_to

            req.request_to = target_profile.user
            req.current_level = next_role
            req.escalate_at = None  # clear after escalation
            req.save(update_fields=["request_to", "current_level", "escalate_at"])

            RequestHistory.objects.create(
                request=req,
                action="auto_escalated",
                from_role=old_role,
                to_role=next_role,
                actor=None,
                note=f"Auto escalated from {old_role} to {next_role}",
            )

            # email to student
            send_request_email(
                subject=f"[{req.request_code}] Request auto-escalated",
                message=(
                    f"Hi {_full_name_or_username(req.student)},\n\n"
                    f"Your permission request has been auto-escalated.\n\n"
                    f"Request ID: {req.request_code}\n"
                    f"Title: {req.title}\n"
                    f"Moved from: {old_role.upper()} to {next_role.upper()}\n"
                ),
                to_email=req.student.email,
            )

            # email to new receiver
            send_request_email(
                subject=f"[{req.request_code}] New permission request assigned to you",
                message=(
                    f"Hello {_full_name_or_username(target_profile.user)},\n\n"
                    f"A permission request has been assigned to you.\n\n"
                    f"Request ID: {req.request_code}\n"
                    f"Title: {req.title}\n"
                    f"Requested by: {_full_name_or_username(req.student)} ({req.student.username})\n"
                    f"Current Level: {next_role.upper()}\n"
                ),
                to_email=target_profile.user.email,
            )

            updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. Warning emails sent: {warned} | Auto-escalated: {updated}"
        ))
