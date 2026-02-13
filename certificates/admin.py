from django.contrib import admin
from .models import Semester, Subject, StudentMark, CertificateRequest, IssuedCertificate

admin.site.register(Semester)
admin.site.register(Subject)
admin.site.register(StudentMark)
admin.site.register(CertificateRequest)
admin.site.register(IssuedCertificate)
