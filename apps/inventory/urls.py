from django.urls import path
from .views import (
    hostel_list_view,
    student_explorer_view,
    warden_bed_map_view,
    admin_warden_assignments_view,
    room_change_requests_view,
    create_hostel_view,
    create_floor_view,
    create_room_view,
    delete_room_view,
    create_bed_view,
    delete_bed_view,
)

app_name = "inventory"

urlpatterns = [
    path("", hostel_list_view, name="list"),
    path("explorer/", student_explorer_view, name="explorer"),
    path("bed-map/", warden_bed_map_view, name="bed_map"),
    path("bed-map/<uuid:hostel_id>/", warden_bed_map_view, name="bed_map_hostel"),
    path("warden-assignments/", admin_warden_assignments_view, name="warden_assignments"),
    path("room-changes/", room_change_requests_view, name="room_changes"),
    path("hostels/create/", create_hostel_view, name="create_hostel"),
    path("floors/create/", create_floor_view, name="create_floor"),
    path("rooms/create/", create_room_view, name="create_room"),
    path("rooms/<uuid:room_id>/delete/", delete_room_view, name="delete_room"),
    path("beds/create/", create_bed_view, name="create_bed"),
    path("beds/<uuid:bed_id>/delete/", delete_bed_view, name="delete_bed"),
]
