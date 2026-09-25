from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register_view, name="register"),
    path("verify-phone/", views.verify_phone_view, name="verify_phone"),
    path("verify-phone/resend/", views.resend_phone_otp_view, name="resend_phone_otp"),
    path("login/", views.login_view, name="login"),
    path("login/2fa/", views.verify_2fa_view, name="verify_2fa"),
    path("logout/", views.logout_view, name="logout"),
    path("2fa/setup/", views.setup_2fa_view, name="setup_2fa"),
    path("2fa/disable/", views.disable_2fa_view, name="disable_2fa"),
    path("me/", views.account_view, name="account"),
]
