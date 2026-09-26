from django.urls import path
from .views import preferences_list_view, roommate_requests_hub_view

app_name = "preferences"

urlpatterns = [
    path("", preferences_list_view, name="list"),
    path("requests/", roommate_requests_hub_view, name="requests"),
]
