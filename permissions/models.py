from django.db import models
from django.contrib.auth.models import User
import os


def permission_upload_path(instance, filename):
    """
    Files go to:
    media/permissions/<REQUEST_CODE>/<REQUEST_CODE>.<ext>

    If request_code is not yet available (first save),
    temporarily store under REQ-TMP.
    """
    ext = os.path.splitext(filename)[1]  # .pdf, .docx etc
    code = instance.request_code or "REQ-TMP"
    return f"permissions/view/33/media/permissions/{code}{ext}"
    #return f"permissions/{code}/{code}{ext}"


class PermissionRequest(models.Model):

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    # ❗ DO NOT make this non-nullable initially
    request_code = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True
    )

    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="requests_made"
    )

    request_to = models.ForeignKey(
        User,
        related_name="requests_received",
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    title = models.CharField(max_length=100)
    reason = models.TextField()

    from_date = models.DateField()
    to_date = models.DateField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )

    current_level = models.CharField(max_length=50, default="proctor")

    # escalation
    is_urgent = models.BooleanField(default=False)
    escalate_at = models.DateTimeField(null=True, blank=True)

    applied_at = models.DateTimeField(auto_now_add=True)
    warning_sent_at = models.DateTimeField(null=True, blank=True)


    file = models.FileField(
        upload_to=permission_upload_path,
        null=True,
        blank=True
    )

    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        """
        1️⃣ First save → get PK
        2️⃣ Generate request_code
        3️⃣ Save again ONLY if needed
        """
        creating = self.pk is None
        super().save(*args, **kwargs)

        if creating and not self.request_code:
            self.request_code = f"REQ-{self.pk:06d}"
            super().save(update_fields=["request_code"])

    def __str__(self):
        return f"{self.request_code} | {self.title} | {self.student.username}"


class RequestHistory(models.Model):

    ACTION_CHOICES = [
        ("created", "Created"),
        ("forwarded", "Forwarded"),
        ("auto_escalated", "Auto Escalated"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("reassigned", "Reassigned"),

        ("urgent_warning_sent", "Urgent Warning Sent")

    ]

    request = models.ForeignKey(
        PermissionRequest,
        on_delete=models.CASCADE,
        related_name="history"
    )

    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    from_role = models.CharField(max_length=20, blank=True, null=True)
    to_role = models.CharField(max_length=20, blank=True, null=True)

    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    note = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.request.request_code} - {self.action}"
