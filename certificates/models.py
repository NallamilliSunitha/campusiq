from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import os

CERT_TYPES = [
    ("study", "Study Certificate"),
    ("bonafide", "Bonafide Certificate"),
    ("tc", "Transfer Certificate"),
    ("marks_memo", "Marks Memo"),
]

STATUS = [
    ("pending", "Pending"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
]


def cert_pdf_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1] or ".pdf"
    code = instance.cert_code or "CERT-TMP"
    return f"certificates/{code}/{code}{ext}"


class Semester(models.Model):
    name = models.CharField(max_length=50)
    order = models.PositiveIntegerField(default=1)

    def __str__(self):
        return self.name


class Subject(models.Model):
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=120)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.code} - {self.name}"


class StudentMark(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    marks = models.DecimalField(max_digits=6, decimal_places=2)
    max_marks = models.DecimalField(max_digits=6, decimal_places=2, default=100)

    class Meta:
        unique_together = ("student", "subject")

    def __str__(self):
        return f"{self.student.username} - {self.subject.code}"


class CertificateRequest(models.Model):
    request_code = models.CharField(max_length=20, unique=True, blank=True)
    cert_type = models.CharField(max_length=20, choices=CERT_TYPES)
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="cert_requests_made")
    request_to = models.ForeignKey(User, on_delete=models.CASCADE, related_name="cert_requests_received")
    status = models.CharField(max_length=20, choices=STATUS, default="pending")
    purpose = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and not self.request_code:
            self.request_code = f"CERTREQ-{self.pk:06d}"
            super().save(update_fields=["request_code"])

    def __str__(self):
        return f"{self.request_code} - {self.cert_type} - {self.student.username}"


class IssuedCertificate(models.Model):
    request = models.OneToOneField(CertificateRequest, on_delete=models.CASCADE, related_name="issued")
    cert_code = models.CharField(max_length=20, unique=True, blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    pdf_file = models.FileField(upload_to=cert_pdf_upload_path, null=True, blank=True)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and not self.cert_code:
            self.cert_code = f"CERT-{self.pk:06d}"
            super().save(update_fields=["cert_code"])
    

    def __str__(self):
        return self.cert_code
    

def cert_attachment_path(instance, filename):
    ext = os.path.splitext(filename)[1]
    code = instance.request.request_code or "CERT-TMP"
    return f"certificates/{code}/attachments/{code}-{instance.id or 'tmp'}{ext}"

class CertificateAttachment(models.Model):
    request = models.ForeignKey(
        "CertificateRequest",
        on_delete=models.CASCADE,
        related_name="attachments"
    )
    file = models.FileField(upload_to=cert_attachment_path)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.request.request_code} attachment"

