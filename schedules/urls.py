from django.urls import path
from . import views

urlpatterns = [
    path("browse/", views.browse_schedules, name="browse_schedules"),
    path("my-availability/", views.my_availability, name="my_availability"),
    path("my-availability/new/", views.my_availability_create, name="my_availability_create"),
    path("my-availability/<int:pk>/edit/", views.my_availability_update, name="my_availability_update"),
    path("manage/<slug:resource>/", views.resource_list, name="resource_list"),
    path("room-utilization/", views.room_utilization_dashboard, name="room_utilization"),
    path("room-utilization/export/csv/", views.export_room_utilization_csv, name="room_utilization_csv"),
    path("room-utilization/export/pdf/", views.export_room_utilization_pdf, name="room_utilization_pdf"),
    path("manage/<slug:resource>/new/", views.resource_create, name="resource_create"),
    path("manage/<slug:resource>/<int:pk>/edit/", views.resource_update, name="resource_update"),
    path("manage/<slug:resource>/<int:pk>/delete/", views.resource_delete, name="resource_delete"),
    path("generate/", views.generate_schedule, name="generate_schedule"),
    path("<int:pk>/", views.schedule_detail, name="schedule_detail"),
    path("<int:pk>/entry/new/", views.entry_create, name="entry_create"),
    path("<int:pk>/entry/<int:entry_pk>/edit/", views.entry_update, name="entry_update"),
    path("<int:pk>/publish/", views.publish_schedule, name="publish_schedule"),
    path("<int:pk>/export/csv/", views.export_csv, name="export_csv"),
    path("<int:pk>/export/pdf/", views.export_pdf, name="export_pdf"),
]
