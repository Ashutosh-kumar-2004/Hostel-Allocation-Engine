from django.shortcuts import render, redirect
from django.db.models import Q
from django.contrib import messages
from .models import Application, AllocationCycle
from apps.eligibility.services import EligibilityService

def application_list_view(request):
    cycles = AllocationCycle.objects.all().order_by("-created_at")
    active_cycle = AllocationCycle.objects.filter(status__in=["OPEN", "PROCESSING", "REVIEW"]).first() or cycles.first()

    # Pre-fill student info if logged in
    user_app = None
    if request.user.is_authenticated:
        user_app = Application.objects.filter(
            Q(user=request.user) |
            Q(student_id=request.user.username) |
            Q(student_email__iexact=request.user.email)
        ).first()

    if request.method == "POST":
        action = request.POST.get("action", "submit_application")
        
        # 1. Action: Submit New Application (Intake)
        if action == "submit_application":
            student_id = request.POST.get("student_id", "").strip()
            student_name = request.POST.get("student_name", "").strip()
            student_email = request.POST.get("student_email", "").strip()
            phone_number = request.POST.get("phone_number", "").strip()
            gender = request.POST.get("gender", "M").strip()
            programme = request.POST.get("programme", "B.Tech Computer Science").strip()
            year_of_study = int(request.POST.get("year_of_study", 1) or 1)
            requires_accessible = request.POST.get("requires_accessible_room") == "on"
            cycle_id = request.POST.get("cycle_id")
            distance_km = float(request.POST.get("distance_from_campus_km") or 50.0)
            cgpa = float(request.POST.get("cgpa") or 8.0)
            address = request.POST.get("address", "").strip()
            fee_cleared = request.POST.get("fee_cleared") in ["on", "true", "True", "1"]

            target_cycle = AllocationCycle.objects.filter(id=cycle_id).first() if cycle_id else active_cycle
            if not target_cycle:
                messages.error(request, "No active allotment cycle is currently available.")
                return redirect("applications:list")

            if not student_id or not student_name or not student_email:
                messages.error(request, "Please enter required fields: Student ID (123XXX), Full Name, and Email.")
                return redirect("applications:list")

            # Check if application already exists for this student & cycle
            existing_app = Application.objects.filter(cycle=target_cycle, student_id=student_id).first()
            if existing_app:
                # Update existing application
                existing_app.student_name = student_name
                existing_app.student_email = student_email
                existing_app.phone_number = phone_number
                existing_app.gender = gender
                existing_app.programme = programme
                existing_app.year_of_study = year_of_study
                existing_app.requires_accessible_room = requires_accessible
                existing_app.distance_from_campus_km = distance_km
                existing_app.cgpa = cgpa
                existing_app.address = address
                existing_app.fee_cleared = fee_cleared
                if request.user.is_authenticated and not existing_app.user:
                    existing_app.user = request.user
                existing_app.save()

                # Evaluate eligibility automatically
                try:
                    EligibilityService.evaluate_application(existing_app)
                except Exception:
                    pass

                messages.success(request, f"Application for Student {student_id} ({student_name}) has been successfully updated!")
            else:
                new_app = Application.objects.create(
                    cycle=target_cycle,
                    user=request.user if request.user.is_authenticated else None,
                    student_id=student_id,
                    student_name=student_name,
                    student_email=student_email,
                    phone_number=phone_number,
                    gender=gender,
                    programme=programme,
                    year_of_study=year_of_study,
                    requires_accessible_room=requires_accessible,
                    distance_from_campus_km=distance_km,
                    cgpa=cgpa,
                    address=address,
                    fee_cleared=fee_cleared,
                    status="SUBMITTED",
                    institution_id="inst_default"
                )
                # Evaluate eligibility automatically
                try:
                    EligibilityService.evaluate_application(new_app)
                except Exception:
                    pass

                messages.success(request, f"New application successfully submitted for {student_name} (Registration No: {student_id}) in {target_cycle.name}!")

            return redirect("applications:list")

        # 2. Action: Admin update status
        elif action == "update_status" and (request.user.is_superuser or request.user.is_staff):
            app_id = request.POST.get("application_id")
            new_status = request.POST.get("status")
            target = Application.objects.filter(id=app_id).first()
            if target and new_status:
                target.status = new_status
                target.save(update_fields=["status", "updated_at"])
                messages.success(request, f"Status of {target.student_name} ({target.student_id}) updated to {target.get_status_display()}.")
            return redirect("applications:list")

    # Fetch applications based on role
    is_staff_or_admin = request.user.is_authenticated and (request.user.is_superuser or request.user.is_staff)
    if request.user.is_authenticated and not is_staff_or_admin:
        applications = Application.objects.filter(
            Q(user=request.user) | 
            Q(student_id=request.user.username) | 
            Q(student_email__iexact=request.user.email)
        ).select_related("cycle", "compatibility_response").prefetch_related("preferences__preferred_hostel")
    else:
        applications = Application.objects.select_related("cycle", "compatibility_response").prefetch_related("preferences__preferred_hostel").order_by("-created_at")[:60]

    context = {
        "cycles": cycles,
        "active_cycle": active_cycle,
        "applications": applications,
        "user_app": user_app,
        "is_staff_or_admin": is_staff_or_admin,
    }
    return render(request, "applications/list.html", context)
