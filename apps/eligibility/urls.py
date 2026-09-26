from django.urls import path
from .views import rules_list_view, run_batch_evaluations_view, student_eligibility_detail_view, update_rule_view

app_name = "eligibility"

urlpatterns = [
    path("", rules_list_view, name="index"),
    path("rules/", rules_list_view, name="rules"),
    path("rules/<uuid:rule_id>/edit/", update_rule_view, name="update_rule"),
    path("run-batch/", run_batch_evaluations_view, name="run_batch"),
    path("status/<uuid:application_id>/", student_eligibility_detail_view, name="status_detail"),
]
