from django.conf import settings
from django.core.mail import send_mail


def _full_name_or_username(user):
    full = (user.get_full_name() or "").strip()
    return full if full else user.username


def send_request_email(subject, message, to_email):
    if not to_email:
        return

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[to_email],
        fail_silently=True,
    )
