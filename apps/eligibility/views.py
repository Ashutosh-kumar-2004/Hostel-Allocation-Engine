from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from apps.core.decorators import warden_or_admin_required
from .models import EligibilityRule, EligibilityResult
from .services import EligibilityService
from apps.applications.models import Application

def rules_list_view(request):
    """
    M3 Policy Rules Console:
    - Lists active institutional policies (Distance, Academic, Disciplinary, Fees).
    - Displays overall intake qualification metrics.
    - Shows batch evaluation table with pass/fail reasons.
    """
    rules = EligibilityRule.objects.select_related("cycle").all().order_by("rule_type")

    # Overall Intake Metrics
    total_apps = Application.objects.count()
    eligible_count = Application.objects.filter(status__in=["ELIGIBLE", "ALLOCATED", "PUBLISHED"]).count()
    ineligible_count = Application.objects.filter(status="INELIGIBLE").count()
    pending_count = Application.objects.filter(status="SUBMITTED").count()

    # Evaluated applications query
    status_filter = request.GET.get("status", "ALL")
    search_q = request.GET.get("q", "").strip()

    apps_qs = Application.objects.select_related("cycle").prefetch_related("eligibility_results", "eligibility_results__rule").all()

    if status_filter == "ELIGIBLE":
        apps_qs = apps_qs.filter(status__in=["ELIGIBLE", "ALLOCATED", "PUBLISHED"])
    elif status_filter == "INELIGIBLE":
        apps_qs = apps_qs.filter(status="INELIGIBLE")
    elif status_filter == "SUBMITTED":
        apps_qs = apps_qs.filter(status="SUBMITTED")

    if search_q:
        apps_qs = apps_qs.filter(
            Q(student_name__icontains=search_q) |
            Q(student_id__icontains=search_q) |
            Q(student_email__icontains=search_q)
        )

    applications_list = apps_qs.order_by("-updated_at")[:60]

    context = {
        "rules": rules,
        "total_applications": total_apps,
        "eligible_count": eligible_count,
        "ineligible_count": ineligible_count,
        "pending_count": pending_count,
        "applications": applications_list,
        "status_filter": status_filter,
        "search_query": search_q,
    }
    return render(request, "eligibility/rules.html", context)


@login_required
@warden_or_admin_required
def run_batch_evaluations_view(request):
    """
    Triggers batch eligibility evaluation for all applicants in the active cycle.
    """
    if request.method == "POST":
        cycle_id = request.POST.get("cycle_id")
        res = EligibilityService.evaluate_all(cycle_id=cycle_id)
        messages.success(
            request,
            f"Batch Eligibility Evaluation completed! {res['total_evaluated']} applications evaluated: "
            f"{res['eligible_count']} Qualified Eligible, {res['ineligible_count']} Ineligible."
        )
    return redirect("eligibility:rules")


@login_required
@warden_or_admin_required
def update_rule_view(request, rule_id):
    """
    Updates rule parameters (e.g. min distance, min CGPA, hard bar flag) and re-evaluates all applicants.
    """
    rule = get_object_or_404(EligibilityRule, id=rule_id)
    if request.method == "POST":
        rule.name = request.POST.get("name", rule.name).strip()
        rule.is_hard_rule = request.POST.get("is_hard_rule") == "on"

        params = dict(rule.parameters or {})
        if rule.rule_type == "DISTANCE":
            params["min_distance_km"] = float(request.POST.get("min_distance_km") or 30.0)
        elif rule.rule_type == "ACADEMIC":
            params["min_cgpa"] = float(request.POST.get("min_cgpa") or 6.0)
        elif rule.rule_type == "DISCIPLINARY":
            params["max_infractions"] = int(request.POST.get("max_infractions") or 0)
        elif rule.rule_type == "FEE_CLEARED":
            params["require_clearance"] = request.POST.get("require_clearance") == "on"

        rule.parameters = params
        rule.save()

        # Re-evaluate all applicants against updated policy thresholds
        res = EligibilityService.evaluate_all(cycle_id=rule.cycle_id)
        messages.success(
            request,
            f"Policy Rule '{rule.name}' updated successfully! Recalculated {res['total_evaluated']} applicants: "
            f"{res['eligible_count']} Qualified Eligible, {res['ineligible_count']} Disqualified."
        )

    return redirect("eligibility:rules")


@login_required
def student_eligibility_detail_view(request, application_id):
    """
    Student-facing / Warden-facing detailed checklist view for a specific student's eligibility results.
    """
    application = get_object_or_404(Application.objects.select_related("cycle"), id=application_id)

    # Security check: If student, ensure they only view their own
    user = request.user
    is_staff = user.is_staff or user.is_superuser or "warden" in user.username.lower() or "warden" in (user.email or "").lower()
    if not is_staff and user.username != application.student_id and user.email != application.student_email:
        messages.error(request, "Access restricted: You may only view your own institutional eligibility record.")
        return redirect("applications:list")

    results = EligibilityResult.objects.filter(application=application).select_related("rule")

    context = {
        "application": application,
        "results": results,
    }
    return render(request, "eligibility/student_status.html", context)
