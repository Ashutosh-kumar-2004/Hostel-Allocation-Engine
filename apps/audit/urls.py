from django.urls import path
from .views import audit_log_view

app_name = "audit"

urlpatterns = [
    path("", audit_log_view, name="log"),
]
