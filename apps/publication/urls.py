from django.urls import path
from .views import (
    publications_view,
    official_allotment_letter_view,
    check_in_student_view,
    verify_document_view
)

app_name = "publication"

urlpatterns = [
    path("", publications_view, name="list"),
    path("letter/<str:document_reference>/", official_allotment_letter_view, name="letter_document"),
    path("check-in/<uuid:letter_id>/", check_in_student_view, name="check_in_student"),
    path("verify/<str:document_reference>/", verify_document_view, name="verify_document"),
]
