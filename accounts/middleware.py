from django.contrib.auth import logout
from django.shortcuts import redirect


class PhoneVerificationRequiredMiddleware:
    """Prevent authenticated accounts with an unverified phone from accessing any protected page."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and not getattr(user, "phone_verified", False):
            logout(request)
            return redirect("accounts:login")
        return self.get_response(request)
