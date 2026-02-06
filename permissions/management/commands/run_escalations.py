from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from django.contrib.auth.models import User
from permissions.models import PermissionRequest, RequestHistory
from accounts.models import UserProfile


ROLE_CHAIN = ["proctor", "staff", "hod", "dean", "principal"]


def _next_role(current_role: str):
    r = (current_role or "").strip().lower()
    if r not in ROLE_CHAIN:
        return None
    i = ROLE_CHAIN.index(r)
    if i + 1 >= len(ROLE_CHAIN):
        return None
    return ROLE_CHAIN[i + 1]


def _pick_user_for_role(role: str, department: str):
    qs = UserProfile.objects.filter(role=role)
    if department:
        qs = qs.filter(department=department)
    p = qs.select_related("user").first()
    return p.user if p else None


class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        now = timezone.now()

        qs = PermissionRequest.objects.filter(status="pending").select_related("student", "request_to")

        updated = 0
        for req in qs:
            if req.escalate_at is None:
                normal_hours = getattr(settings, "NORMAL_ESCALATION_HOURS", 24)
                req.escalate_at = req.applied_at + timezone.timedelta(hours=normal_hours)
                req.save(update_fields=["escalate_at"])
                continue

            if req.escalate_at > now:
                continue

            student_profile = UserProfile.objects.filter(user=req.student).first()
            dept = student_profile.department if student_profile else ""

            cur_role = (req.current_level or "").strip().lower()
            nxt = _next_role(cur_role)
            if not nxt:
                req.escalate_at = None
                req.save(update_fields=["escalate_at"])
                continue

            target_user = _pick_user_for_role(nxt, dept)
            if not target_user:
                req.escalate_at = now + timezone.timedelta(minutes=30)
                req.save(update_fields=["escalate_at"])
                continue

            old_role = cur_role
            req.request_to = target_user
            req.current_level = nxt

            normal_hours = getattr(settings, "NORMAL_ESCALATION_HOURS", 24)
            req.escalate_at = now + timezone.timedelta(hours=normal_hours)

            req.save(update_fields=["request_to", "current_level", "escalate_at"])

            RequestHistory.objects.create(
                request=req,
                action="auto_escalated",
                from_role=old_role,
                to_role=nxt,
                actor=None,
                note="Auto escalated by system"
            )

            updated += 1

        self.stdout.write(self.style.SUCCESS(f"Auto escalation done. Updated: {updated}"))
