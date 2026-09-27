from django.urls import path
from .views import (
    draft_list_view,
    draft_detail_view,
    student_explanation_view,
    what_if_simulation_view,
    trigger_allocation_view,
)

app_name = "allocation"

urlpatterns = [
    path("drafts/", draft_list_view, name="draft_list"),
    path("trigger/", trigger_allocation_view, name="trigger"),
    path("drafts/<uuid:draft_id>/", draft_detail_view, name="draft_detail"),
    path("explanation/<uuid:assignment_id>/", student_explanation_view, name="explanation"),
    path("simulation/", what_if_simulation_view, name="simulation"),
]
