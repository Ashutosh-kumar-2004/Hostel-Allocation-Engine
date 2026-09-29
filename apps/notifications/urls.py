from django.urls import path
from .views import mark_read_and_redirect_view, mark_all_read_view

app_name = "notifications"

urlpatterns = [
    path("read/<uuid:notification_id>/", mark_read_and_redirect_view, name="mark_read"),
    path("mark-all-read/", mark_all_read_view, name="mark_all_read"),
]
