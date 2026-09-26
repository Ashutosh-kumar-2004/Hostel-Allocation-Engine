from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q
from .models import CompatibilityResponse
from .services import CompatibilityService
from apps.inventory.models import Hostel, WardenHostelAssignment
from apps.applications.models import Application, AllocationCycle
from apps.preferences.models import Preference
from apps.preferences.services import PreferenceService

def compatibility_info_view(request):
    """
    Module 5: Lifestyle Compatibility & Consent Protection (DPDP Act 2023 Compliant)
    - Students: Submit/Edit questionnaire, view privacy shield status, and preview mutual partner compatibility.
    - Wardens: Jurisdiction-scoped cohort harmony analytics, mutual pairs compatibility, and live simulator.
    - Admins: Campus-wide cohort distributions, DPDP compliance metrics, and pairwise simulator sandbox.
    """
    warden_assignment = None
    if request.user.is_authenticated:
        warden_assignment = WardenHostelAssignment.objects.filter(
            Q(user=request.user) | Q(warden_email__iexact=request.user.email)
        ).select_related("hostel").first()

    is_warden = bool(warden_assignment or (request.user.is_authenticated and ("warden" in request.user.username.lower() or "warden" in (request.user.email or "").lower())))
    is_admin = bool(request.user.is_authenticated and (request.user.is_superuser or (request.user.is_staff and not is_warden)))
    is_student = bool(request.user.is_authenticated and not is_admin and not is_warden)

    warden_hostel = warden_assignment.hostel if warden_assignment else None
    if is_warden and not warden_hostel:
        warden_hostel = Hostel.objects.filter(is_active=True).first()

    # Find student's active application if authenticated
    user_app = None
    user_response = None
    if request.user.is_authenticated:
        user_app = getattr(request.user, "student_application", None)
        if not user_app:
            user_app = Application.objects.filter(
                Q(user=request.user) |
                Q(student_id=request.user.username) |
                Q(student_email__iexact=request.user.email)
            ).first()
        if user_app:
            user_response = CompatibilityResponse.objects.filter(application=user_app).first()

    # Handle questionnaire submission / update (POST)
    if request.method == "POST":
        if not request.user.is_authenticated:
            messages.error(request, "Please log in to submit your lifestyle preferences.")
            return redirect("login")

        app_id = request.POST.get("application_id")
        target_app = user_app
        if (is_admin or is_warden) and app_id:
            target_app = Application.objects.filter(id=app_id).first()

        if not target_app:
            messages.error(request, "An active student application is required to submit lifestyle compatibility data.")
            return redirect("applications:list")

        sleep_habit = request.POST.get("sleep_habit", "FLEXIBLE").strip()
        study_environment = request.POST.get("study_environment", "LIGHT_MUSIC").strip()
        cleanliness_priority = request.POST.get("cleanliness_priority", "MODERATE").strip()
        guest_tolerance = int(request.POST.get("guest_tolerance_score", 3) or 3)
        consent_recorded = request.POST.get("consent_recorded") in ["on", "true", "True", "1"]

        if not consent_recorded:
            messages.error(request, "Explicit consent under the DPDP Act 2023 is mandatory to process lifestyle preferences for co-allocation.")
            return redirect("compatibility:info")

        # Validate choices
        valid_sleep = dict(CompatibilityResponse.SLEEP_HABIT_CHOICES).keys()
        valid_study = dict(CompatibilityResponse.STUDY_ENVIRONMENT_CHOICES).keys()
        valid_clean = dict(CompatibilityResponse.CLEANLINESS_CHOICES).keys()

        if sleep_habit not in valid_sleep or study_environment not in valid_study or cleanliness_priority not in valid_clean:
            messages.error(request, "Invalid questionnaire options submitted.")
            return redirect("compatibility:info")

        guest_tolerance = max(1, min(5, guest_tolerance))

        CompatibilityResponse.objects.update_or_create(
            application=target_app,
            defaults={
                "sleep_habit": sleep_habit,
                "study_environment": study_environment,
                "cleanliness_priority": cleanliness_priority,
                "guest_tolerance_score": guest_tolerance,
                "consent_recorded": True,
                "institution_id": target_app.institution_id or "inst_default",
            }
        )
        messages.success(request, f"Lifestyle questionnaire and DPDP Act 2023 consent recorded successfully for {target_app.student_name}!")
        return redirect("compatibility:info")

    # Mutual partner alignment calculation for student
    mutual_status = None
    mutual_partner_breakdown = None
    partner_app = None
    if user_app:
        mutual_status = PreferenceService.check_roommate_mutual_status(user_app)
        partner_id = mutual_status.get("target_id")
        if partner_id:
            partner_app = Application.objects.filter(cycle=user_app.cycle, student_id=partner_id).first()
            if partner_app:
                mutual_partner_breakdown = CompatibilityService.get_detailed_breakdown(user_app, partner_app)

    # Scoped analytics and confirmed mutual pairs
    scoped_hostel_id = warden_hostel.id if is_warden and warden_hostel else None
    cohort_stats = None
    mutual_pairs_compatibility = []
    candidate_applicants = []
    simulation_result = None
    sim_student_a_id = request.GET.get("sim_a", "").strip()
    sim_student_b_id = request.GET.get("sim_b", "").strip()

    if is_admin or is_warden:
        cohort_stats = CompatibilityService.get_cohort_compatibility_stats(hostel_id=scoped_hostel_id)
        mutual_pairs_compatibility = CompatibilityService.get_mutual_pairs_compatibility(hostel_id=scoped_hostel_id)

        # Simulator applicants
        if is_warden and warden_hostel:
            candidate_applicants = Application.objects.filter(preferences__preferred_hostel=warden_hostel).distinct().order_by("student_name")
        else:
            candidate_applicants = Application.objects.all().order_by("student_name")

        if sim_student_a_id and sim_student_b_id and sim_student_a_id != sim_student_b_id:
            student_a = Application.objects.filter(id=sim_student_a_id).first()
            student_b = Application.objects.filter(id=sim_student_b_id).first()
            if student_a and student_b:
                gender_match = (student_a.gender == student_b.gender)
                simulation_result = {
                    "student_a": student_a,
                    "student_b": student_b,
                    "gender_match": gender_match,
                    "breakdown": CompatibilityService.get_detailed_breakdown(student_a, student_b),
                }

    context = {
        "user_app": user_app,
        "user_response": user_response,
        "mutual_status": mutual_status,
        "partner_app": partner_app,
        "mutual_partner_breakdown": mutual_partner_breakdown,
        "cohort_stats": cohort_stats,
        "mutual_pairs_compatibility": mutual_pairs_compatibility,
        "candidate_applicants": candidate_applicants,
        "simulation_result": simulation_result,
        "sim_student_a_id": sim_student_a_id,
        "sim_student_b_id": sim_student_b_id,
        "is_admin": is_admin,
        "is_warden": is_warden,
        "is_student": is_student,
        "warden_hostel": warden_hostel,
        "sleep_choices": CompatibilityResponse.SLEEP_HABIT_CHOICES,
        "study_choices": CompatibilityResponse.STUDY_ENVIRONMENT_CHOICES,
        "cleanliness_choices": CompatibilityResponse.CLEANLINESS_CHOICES,
    }
    return render(request, "compatibility/info.html", context)
