from django.contrib import admin
from django.urls import include, path
from schedules import views
from django.contrib.auth.views import LoginView
from schedules.auth_forms import LimitedAuthenticationForm

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", LoginView.as_view(authentication_form=LimitedAuthenticationForm), name="login"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", views.landing_page, name="landing"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("schedules/", include("schedules.urls")),
]
