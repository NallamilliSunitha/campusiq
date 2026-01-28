from django.contrib import admin
from .models import PermissionRequest

@admin.register(PermissionRequest)
class PermissionRequestAdmin(admin.ModelAdmin):
    list_display = ('student', 'from_date', 'to_date', 'status', 'current_level')
    list_filter = ('status',)
