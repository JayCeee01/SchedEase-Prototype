from django.contrib import admin
from django.urls import include, path
from schedules import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", views.dashboard, name="dashboard"),
    path("schedules/", include("schedules.urls")),
]
