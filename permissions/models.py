from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

class PermissionRequest(models.Model):
   
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

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

    # ✅ NEW FIELD
    title = models.CharField(max_length=100)

    reason = models.TextField()
    from_date = models.DateField()
    to_date = models.DateField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )

    current_level = models.CharField(max_length=50, default='proctor')
    is_urgent = models.BooleanField(default=False)
    escalate_at = models.DateTimeField(null=True, blank=True)

    applied_at = models.DateTimeField(auto_now_add=True)
    file = models.FileField(upload_to="permissions/", null=True, blank=True)
    

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} | {self.student.username} → {self.request_to.username if self.request_to else 'N/A'}"
    
class RequestHistory(models.Model):
    ACTION_CHOICES = [
        ("created", "Created"),
        ("forwarded", "Forwarded"),
        ("auto_escalated", "Auto Escalated"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
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
        return f"{self.request_id} - {self.action}"
