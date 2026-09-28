from django.urls import path
from .views import (
    waitlist_view,
    student_waitlist_status_view,
    auto_promote_vacancies_view,
    student_respond_offer_view,
    manual_offer_bed_view,
)

app_name = "waitlist"

urlpatterns = [
    path("", waitlist_view, name="list"),
    path("my-status/", student_waitlist_status_view, name="my_status"),
    path("auto-promote/", auto_promote_vacancies_view, name="auto_promote"),
    path("offers/<uuid:entry_id>/respond/", student_respond_offer_view, name="respond_offer"),
    path("offers/<uuid:entry_id>/manual-offer/", manual_offer_bed_view, name="manual_offer"),
]
