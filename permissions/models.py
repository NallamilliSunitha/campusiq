from django.db import models
from django.contrib.auth.models import User

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
    file = models.FileField(upload_to='permission_files/', null=True, blank=True)

    applied_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} | {self.student.username} → {self.request_to.username if self.request_to else 'N/A'}"
