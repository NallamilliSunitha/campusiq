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

    def __str__(self):
        return f"{self.user.username} - {self.role}"

