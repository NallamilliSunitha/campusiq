from django.urls import path
from . import views

urlpatterns = [
    path("apply/", views.apply_certificate, name="apply_certificate"),
    path("my/", views.my_certificates, name="my_certificates"),

    path("received/", views.received_certificate_requests, name="received_certificate_requests"),
  

    path("approve/<int:id>/", views.approve_certificate_request, name="approve_certificate_request"),
    path("reject/<int:id>/", views.reject_certificate_request, name="reject_certificate_request"),
    path("forward/<int:id>/", views.forward_certificate_to_principal, name="forward_certificate_to_principal"),

    path("view/<int:id>/", views.view_certificate, name="view_certificate"),
    path("verify/<str:code>/", views.verify_certificate, name="verify_certificate"),

    path("download/<int:id>/", views.download_certificate_pdf, name="download_certificate_pdf"),
    path("qr/<str:code>/", views.certificate_qr, name="certificate_qr"),
    path("review/<int:id>/", views.review_certificate_request, name="review_certificate_request"),

]
