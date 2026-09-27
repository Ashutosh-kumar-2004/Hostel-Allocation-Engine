from django.urls import path
from .views import (
    review_dashboard_view,
    draft_review_view,
    apply_override_view,
    swap_residents_view,
    approve_draft_view,
    approve_and_publish_draft_view,
    overrides_log_view,
)

app_name = "review"

urlpatterns = [
    path("", review_dashboard_view, name="dashboard"),
    path("drafts/<uuid:draft_id>/", draft_review_view, name="draft_review"),
    path("drafts/<uuid:draft_id>/override/", apply_override_view, name="apply_override"),
    path("drafts/<uuid:draft_id>/swap/", swap_residents_view, name="swap_residents"),
    path("drafts/<uuid:draft_id>/approve/", approve_draft_view, name="approve_draft"),
    path("drafts/<uuid:draft_id>/approve-publish/", approve_and_publish_draft_view, name="approve_publish"),
    path("drafts/<uuid:draft_id>/overrides-log/", overrides_log_view, name="overrides_log"),
]
