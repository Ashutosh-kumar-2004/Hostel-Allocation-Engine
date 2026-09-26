from django.urls import path
from .views import compatibility_info_view

app_name = "compatibility"

urlpatterns = [
    path("", compatibility_info_view, name="info"),
]
