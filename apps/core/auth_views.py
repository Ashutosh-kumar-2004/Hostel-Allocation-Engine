import re
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.db import transaction
from django.utils import timezone
from apps.applications.models import AllocationCycle, Application
from apps.inventory.models import Hostel, Room
from apps.preferences.models import Preference
from apps.compatibility.models import CompatibilityResponse
from apps.audit.models import AuditEntry

User = get_user_model()

def login_view(request):
    """
    Unified Login Portal supporting Students (Registration Number or Username) & Staff/Wardens.
    """
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        identifier = request.POST.get("identifier", "").strip()
        password = request.POST.get("password", "").strip()

        # Check authentication by username first
        user = authenticate(request, username=identifier, password=password)
        if not user:
            # Check if identifier matches student email
            try:
                matched_user = User.objects.get(email__iexact=identifier)
                user = authenticate(request, username=matched_user.username, password=password)
            except User.DoesNotExist:
                user = None

        if user:
            login(request, user)
            messages.success(request, f"Welcome back, {user.first_name or user.username}!")
            next_url = request.GET.get("next", "dashboard")
            return redirect(next_url)
        else:
            messages.error(request, "Invalid registration number/username or password. Please try again.")

    return render(request, "auth/login.html")


def logout_view(request):
    """
    Terminates user session and redirects to login.
    """
    logout(request)
    messages.info(request, "You have been logged out successfully.")
    return redirect("login")


def signup_view(request):
    """
    Student Registration Portal.
    Captures:
    - Registration Number (Format: 123XXX where X is numeric)
    - Full Name, DOB, Address, Email, Phone
    - Gender, Programme, CGPA, Distance from campus
    - Accessibility requirement
    - Preferred Hostel & Room Cooling Type (AC/Cooler/Fan)
    - Consented lifestyle attributes (Sleep, Study, Cleanliness)
    """
    if request.user.is_authenticated:
        return redirect("dashboard")

    active_cycle = AllocationCycle.objects.filter(status="OPEN").order_by("-created_at").first()
    if not active_cycle:
        active_cycle = AllocationCycle.objects.order_by("-created_at").first()

    hostels = Hostel.objects.filter(is_active=True)

    if request.method == "POST":
        reg_number = request.POST.get("reg_number", "").strip().upper()
        full_name = request.POST.get("full_name", "").strip()
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "").strip()
        dob = request.POST.get("dob", "")
        address = request.POST.get("address", "").strip()
        phone = request.POST.get("phone", "").strip()
        gender = request.POST.get("gender", "M")
        programme = request.POST.get("programme", "B.Tech Computer Science")
        distance_km = float(request.POST.get("distance_km", 45.0) or 45.0)
        cgpa = float(request.POST.get("cgpa", 8.0) or 8.0)
        requires_accessible = request.POST.get("requires_accessible", "") == "1"

        # Preferences
        preferred_hostel_id = request.POST.get("preferred_hostel_id")
        preferred_room_type = request.POST.get("preferred_room_type", "DOUBLE")
        preferred_cooling = request.POST.get("preferred_cooling", "AC")

        # Lifestyle Compatibility Answers
        sleep_habit = request.POST.get("sleep_habit", "FLEXIBLE")
        study_env = request.POST.get("study_env", "LIGHT_MUSIC")
        cleanliness = request.POST.get("cleanliness", "MODERATE")
        guest_tolerance = int(request.POST.get("guest_tolerance", 3) or 3)

        # 1. Validation: Registration number must follow 123XXXXX pattern (8 digits total: '123' + 5 digits)
        if not re.match(r"^123\d{5}$", reg_number):
            messages.error(request, "Registration Number must follow the format '123XXXXX' (e.g. 12345678).")
            return render(request, "auth/signup.html", {"cycle": active_cycle, "hostels": hostels})

        if User.objects.filter(username=reg_number).exists():
            messages.error(request, f"Registration number {reg_number} is already registered. Please log in.")
            return redirect("login")

        if User.objects.filter(email=email).exists():
            messages.error(request, f"Email {email} is already registered. Please use another email or log in.")
            return render(request, "auth/signup.html", {"cycle": active_cycle, "hostels": hostels})

        try:
            with transaction.atomic():
                # 2. Create Django User
                user = User.objects.create_user(
                    username=reg_number,
                    email=email,
                    password=password,
                    first_name=full_name
                )

                # 3. Create Application Profile
                application = Application.objects.create(
                    cycle=active_cycle,
                    user=user,
                    student_id=reg_number,
                    student_name=full_name,
                    student_email=email,
                    phone_number=phone,
                    dob=dob or None,
                    address=address,
                    gender=gender,
                    programme=programme,
                    distance_from_campus_km=distance_km,
                    cgpa=cgpa,
                    requires_accessible_room=requires_accessible,
                    status="ELIGIBLE" if distance_km >= 30 else "SUBMITTED"
                )

                # 4. Create Ranked Preference
                if preferred_hostel_id:
                    chosen_hostel = Hostel.objects.get(id=preferred_hostel_id)
                    Preference.objects.create(
                        application=application,
                        rank=1,
                        preferred_hostel=chosen_hostel,
                        preferred_room_type=preferred_room_type
                    )

                # 5. Create Consented Compatibility Profile
                CompatibilityResponse.objects.create(
                    application=application,
                    sleep_habit=sleep_habit,
                    study_environment=study_env,
                    cleanliness_priority=cleanliness,
                    guest_tolerance_score=guest_tolerance,
                    consent_recorded=True
                )

                # 6. Immutable Audit Entry
                AuditEntry.objects.create(
                    actor_id=str(user.id),
                    actor_email=email,
                    action="STUDENT_SELF_REGISTRATION",
                    target_entity="Application",
                    target_id=str(application.id),
                    reason=f"Student {full_name} ({reg_number}) registered directly via intake portal."
                )

            # Automatically log in the registered student
            login(request, user)
            messages.success(request, f"Welcome {full_name}! Your registration ({reg_number}) and hostel application have been registered successfully.")
            return redirect("dashboard")

        except Exception as e:
            messages.error(request, f"Registration failed due to system error: {str(e)}")
            return render(request, "auth/signup.html", {"cycle": active_cycle, "hostels": hostels})

    return render(request, "auth/signup.html", {"cycle": active_cycle, "hostels": hostels})
