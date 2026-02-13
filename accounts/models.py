from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone



class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('student', 'Student'),
        ('proctor', 'Proctor'),
        ('staff', 'Staff'),
        ('hod', 'HOD'),
        ('dean', 'Dean'),
        ('principal', 'Principal'),
    ]

    DEPARTMENT_CHOICES = [
        ('CSE', 'Computer Science'),
        ('ECE', 'Electronics'),
        ('MECH', 'Mechanical'),
        ('CIVIL', 'Civil'),
        ('EEE', 'Electrical'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    department = models.CharField(max_length=20, choices=DEPARTMENT_CHOICES)
    roll_number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    signature = models.ImageField(upload_to="signatures/", null=True, blank=True)
    stamp = models.ImageField(upload_to="stamps/", null=True, blank=True)
    designation = models.CharField(max_length=100, blank=True, default="")
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class PasswordResetOTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(default=timezone.now)

    def is_expired(self):
        return timezone.now() > self.created_at + timezone.timedelta(minutes=5)


    def __str__(self):
        return f"{self.user.username} - {self.role}"

