from django.urls import path
from .views import application_list_view

app_name = "applications"

urlpatterns = [
    path("", application_list_view, name="list"),
]
